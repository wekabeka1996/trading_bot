# trading_bot/engine.py
# Основний рушій, який виконує торговий план.
"""Основной рушій, який виконує торговий план."""

import logging
import time
import threading
from datetime import datetime, timedelta
import pytz

from binance.exceptions import (
    BinanceAPIException, BinanceRequestException
)

from trading_bot.plan_parser import (
    PlanParser, TradingPlan, ActiveAsset, OrderGroup
)
from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.risk_manager import RiskManager
from trading_bot.notifications import TelegramNotifier
from trading_bot.journal import TradingJournal
from trading_bot.utils import calculate_atr


class Engine:
    """
    Клас Execution Engine. Відповідає за виконання торгового плану,
    управління ордерами та позиціями.
    """

    def _should_place_new_orders(self) -> bool:
        """
        Free-Margin Guard: перевіряє, чи можна розміщати нові ордери.
        """
        free_margin = self.exchange.get_free_margin()
        total_balance = self.exchange.get_total_balance()
        if free_margin is None or total_balance is None or total_balance == 0:
            self.logger.warning("Не вдалося отримати дані для free-margin guard.")
            return False
        if free_margin / total_balance < 0.20:
            self.logger.warning("Free margin <20 % — new orders paused")
            return False
        return True

    def __init__(
        self,
        plan_parser: PlanParser,
        exchange_connector: BinanceFuturesConnector,
        notifier: TelegramNotifier,
        journal: TradingJournal,
    ):
        self.logger = logging.getLogger(__name__)
        self.plan_parser = plan_parser
        self.exchange = exchange_connector
        self.notifier = notifier
        self.journal = journal
        self.plan: TradingPlan | None = None
        self.risk_manager: RiskManager | None = None
        self.trading_paused = False
        self.executed_phases = set()
        self.managed_positions = {}
        self.oco_orders = {}
        self.price_tracker = {}
        self.last_check_time = datetime.now(pytz.utc)
        self.last_volatility_check = None

    def run(self):
        """Запускає головний цикл бота."""
        self.logger.info("Execution Engine запущено.")
        self.notifier.send_message("Бот запускається...", level="info")
        if not self._initial_setup():
            self.notifier.send_message(
                "Помилка початкового налаштування. Бот зупинено.",
                level="critical"
            )
            return

        try:
            while True:
                current_utc_time = datetime.now(pytz.utc)
                if current_utc_time - self.last_check_time > \
                        timedelta(seconds=15):
                    self._process_trade_phases(current_utc_time)
                    self._monitor_oco_orders()
                    self._manage_open_positions()
                    self._check_global_risks(current_utc_time)
                    self.last_check_time = current_utc_time
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info(
                "Отримано команду зупинки. Завершення роботи..."
            )
            self._handle_shutdown()
        finally:
            self.logger.info("Бот зупинено.")
            self.notifier.send_message("Бот зупинено.", level="warning")

    def _initial_setup(self) -> bool:
        """Виконує початкові перевірки та налаштування."""
        self.logger.info("Виконується початкове налаштування...")
        if not self.exchange.check_connection():
            return False
        if not self.plan_parser.load_and_validate():
            return False
        self.plan = self.plan_parser.get_plan()
        if not self.plan:
            self.logger.error("Не вдалося завантажити торговий план")
            return False
        self.risk_manager = RiskManager(
            plan=self.plan, exchange=self.exchange,
            notifier=self.notifier, journal=self.journal
        )
        
        # Runtime margin guard - перевірка лімітів маржі при завантаженні
        total_margin_required = sum(
            asset.position_size_pct / asset.leverage 
            for asset in self.plan.active_assets
        )
        margin_limit = self.plan.global_settings.margin_limit_pct
        
        assert total_margin_required <= margin_limit, (
            f"Initial margin {total_margin_required:.1%} exceeds limit "
            f"{margin_limit:.1%} – aborting load."
        )
        
        self.logger.info(
            f"✅ Margin check passed: {total_margin_required:.1%} ≤ {margin_limit:.1%}"
        )
        
        self.risk_manager.update_equity()
        self.logger.info(
            "Бот працюватиме за планом: %s - %s",
            self.plan.plan_date, self.plan.plan_type
        )
        self.notifier.send_message(
            f"План '{self.plan.plan_type}' версії "
            f"{self.plan.plan_version} завантажено. Починаю роботу.",
            level="success"
        )
        return True

    def _process_trade_phases(self, current_utc_time: datetime):
        """Обробляє часові фази з торгового плану."""
        if not self.plan or self.trading_paused:
            return
        for phase_name, phase_details in self.plan.trade_phases.items():
            if phase_name in self.executed_phases:
                continue

            # Підтримка обох форматів: time та start_time
            phase_time_str = phase_details.time or phase_details.start_time
            if not phase_time_str:
                self.logger.warning(
                    "Фаза '%s' не має часу виконання", phase_name
                )
                continue

            try:
                local_tz = pytz.timezone('Europe/Kiev')
                plan_date = datetime.strptime(
                    self.plan.plan_date, "%Y-%m-%d"
                ).date()

                # Парсимо час у форматі HH:MM
                if ':' in phase_time_str:
                    hour, minute = map(int, phase_time_str.split(':'))
                else:
                    self.logger.error(
                        "Некоректний формат часу для фази '%s': %s",
                        phase_name, phase_time_str
                    )
                    continue

                phase_local_time = local_tz.localize(
                    datetime.combine(plan_date, datetime.min.time())
                ).replace(hour=hour, minute=minute)
                phase_utc_time = phase_local_time.astimezone(pytz.utc)
            except (ValueError, TypeError) as e:
                self.logger.error(
                    "Некоректний формат часу для фази '%s': %s",
                    phase_name, e
                )
                continue

            # Допускаємо невелику похибку в 30 секунд, щоб не пропустити фазу
            if abs((current_utc_time - phase_utc_time).total_seconds()) <= 30:
                self.logger.info("Настала торгова фаза: '%s'", phase_name)
                if not phase_details.action:
                    self.logger.error(
                        "Для фази '%s' не вказано дію ('action') у "
                        "торговому плані. Фазу пропущено.", phase_name
                    )
                    self.notifier.send_message(
                        f"Помилка в плані: для фази '{phase_name}' "
                        "не вказано дію.", level="critical"
                    )
                    self.executed_phases.add(phase_name)
                    continue

                handler_method_name = f"_handle_{phase_details.action}"
                handler_method = getattr(
                    self, handler_method_name, self._handle_unknown_action
                )
                handler_method()
                self.executed_phases.add(phase_name)

    def _is_within_entry_hours_eest(self, current_utc_time: datetime) -> bool:
        """Глобальна дисципліна часу: заборона нових входів 01:00–08:00 EEST і після 23:00 EEST."""
        try:
            local_tz = pytz.timezone('Europe/Kiev')
            local_time = current_utc_time.astimezone(local_tz)
            hour = local_time.hour
            # Заборона нових входів вночі
            if 1 <= hour < 8:
                return False
            # Після 23:00 — нові входи заборонені
            if hour >= 23:
                return False
            return True
        except Exception as e:
            self.logger.warning(f"Помилка перевірки EEST вікна: {e}")
            return True

    def _should_execute_order_group(
        self, order_group: OrderGroup, current_time: datetime
    ) -> bool:
        """Перевіряє, чи потрібно виконати групу ордерів зараз."""
        try:
            # Парсимо час з урахуванням часової зони
            time_from = datetime.fromisoformat(order_group.time_valid_from)
            time_to = datetime.fromisoformat(order_group.time_valid_to)

            # Переводимо поточний час в ту ж зону
            if time_from.tzinfo:
                current_time = current_time.astimezone(time_from.tzinfo)

            return time_from <= current_time <= time_to
        except (ValueError, TypeError) as e:
            self.logger.error("Помилка при перевірці часу для ордера: %s", e)
            return False

    def _handle_place_all_orders(self):
        """Обробляє розміщення ордерів згідно зі стратегією в плані."""
        self.logger.info("Розміщення ордерів згідно з планом...")
        if not self.plan or not self.risk_manager:
            return

        current_time = datetime.now(pytz.utc)
        # Глобальне EEST-вікно для нових входів
        if not self._is_within_entry_hours_eest(current_time):
            self.logger.warning("Глобальне правило часу (EEST): нові входи тимчасово заборонені")
            return
        for asset in self.plan.active_assets:
            # Перевіряємо статус символу перед розміщенням ордерів
            if not self.exchange.is_symbol_active(asset.symbol):
                self.logger.warning(
                    "Символ %s неактивний або делістований, пропускаємо ордери.",
                    asset.symbol
                )
                self.notifier.send_message(
                    f"⛔ Символ {asset.symbol} неактивний або делістований", 
                    level="warning"
                )
                continue

            if asset.strategy == "oco_breakout":
                # Перевіряємо, чи час валідний для виконання ордерів
                bullish_group = asset.order_groups.get("bullish")

                if bullish_group and self._should_execute_order_group(
                    bullish_group, current_time
                ):
                    self._place_oco_breakout_orders(asset)
                else:
                    self.logger.info(
                        "Час для виконання OCO ордерів %s ще не настав "
                        "або вже минув.", asset.symbol
                    )
            else:
                self.logger.warning(
                    "Стратегія '%s' для %s не є OCO і поки не обробляється.",
                    asset.strategy, asset.symbol
                )

    def _place_oco_breakout_orders(self, asset: ActiveAsset):
        """Розміщує STOP ордери для стратегії пробою (підтримує асиметричні плани)."""
        bullish_group = asset.order_groups.get("bullish")
        bearish_group = asset.order_groups.get("bearish")
        
        # ВИПРАВЛЕНО: дозволяємо асиметричні плани (лише один напрямок)
        if not bullish_group and not bearish_group:
            self.logger.error(
                "Для стратегії пробою потрібна принаймні одна група ордерів "
                "(bullish або bearish) для %s", asset.symbol
            )
            return
        
        if not self.risk_manager:
            return

        # Free-Margin Guard
        if not self._should_place_new_orders():
            self.logger.warning(f"Free-Margin Guard: ордери для {asset.symbol} не будуть розміщені.")
            return

        # Розміщуємо наявні групи (bullish, bearish, або обидві)
        orders_placed = []
        
        if bullish_group:
            try:
                bullish_order = self._place_single_breakout_order(asset, bullish_group, "BUY")
                if bullish_order:
                    orders_placed.append(bullish_order)
                    self.logger.info(f"✅ Bullish ордер для {asset.symbol} розміщено")
            except Exception as e:
                self.logger.error(f"Помилка розміщення bullish ордера для {asset.symbol}: {e}")
        
        if bearish_group:
            try:
                bearish_order = self._place_single_breakout_order(asset, bearish_group, "SELL")
                if bearish_order:
                    orders_placed.append(bearish_order)
                    self.logger.info(f"✅ Bearish ордер для {asset.symbol} розміщено")
            except Exception as e:
                # ВАЖЛИВО: не блокуємо bullish ордер через помилку bearish
                self.logger.error(f"Помилка розміщення bearish ордера для {asset.symbol}: {e}")
        
        if orders_placed:
            self.logger.info(f"Розміщено {len(orders_placed)} ордер(ів) для {asset.symbol}")
        else:
            self.logger.error(f"Не вдалося розмістити жодного ордера для {asset.symbol}")

    def _place_single_breakout_order(self, asset, order_group, side: str):
        """Розміщує окремий ордер пробою."""
        # Захисна перевірка ризик-менеджера
        if not self.risk_manager:
            return None
        # Встановлюємо плече
        try:
            self.exchange.client.futures_change_leverage(
                symbol=asset.symbol, leverage=asset.leverage
            )
            self.logger.info("Плече успішно встановлено: %s x%s", asset.symbol, asset.leverage)
        except Exception as e:
            self.logger.error("Не вдалося встановити плече для %s: %s", asset.symbol, e)
            return None

        # Отримуємо поточну ціну
        current_price = self.exchange.get_current_price(asset.symbol)
        if not current_price or current_price <= 0:
            self.logger.error("Не вдалося отримати валідну ціну для %s", asset.symbol)
            return None

        self.logger.info("Поточна ціна %s: $%.6f", asset.symbol, current_price)

        # Розраховуємо кількість через ризик-менеджер
        quantity = self.risk_manager.calculate_position_size(
            asset, order_group
        )
        if not quantity or quantity <= 0:
            self.logger.error("Не вдалося розрахувати кількість для %s", asset.symbol)
            return None

        # Додаткова перевірка: не ставимо STOP, який спрацює миттєво
        try:
            trigger = float(order_group.trigger_price)
            if side.upper() == "BUY" and trigger <= float(current_price):
                self.logger.info(
                    "Пропущено BUY STOP для %s: trigger %.4f ≤ поточна ціна %.4f (миттєве спрацювання)",
                    asset.symbol, trigger, float(current_price)
                )
                return None
            if side.upper() == "SELL" and trigger >= float(current_price):
                self.logger.info(
                    "Пропущено SELL STOP для %s: trigger %.4f ≥ поточна ціна %.4f (миттєве спрацювання)",
                    asset.symbol, trigger, float(current_price)
                )
                return None
        except Exception:
            # Якщо не вдалося порівняти — перестраховочно не фільтруємо
            pass

        # Формуємо ордер: нормалізуємо тип для Binance Futures
        try:
            raw_type = (order_group.order_type or "").upper()
            is_limit_trigger = "LIMIT" in raw_type
            # Для STOP-LIMIT використовуємо type="STOP" + price + stopPrice
            # Для чистого STOP використовуємо type="STOP_MARKET" + stopPrice
            binance_type = "STOP" if is_limit_trigger else "STOP_MARKET"

            params = {"stopPrice": order_group.trigger_price}
            if is_limit_trigger and getattr(order_group, "limit_price", None) is not None:
                params["price"] = order_group.limit_price
                params["timeInForce"] = "GTC"

            order = self.exchange.place_order(
                symbol=asset.symbol,
                side=side,
                order_type=binance_type,
                quantity=quantity,
                **params
            )
            return order
        except Exception as e:
            self.logger.error(f"Помилка розміщення ордера {side} для {asset.symbol}: {e}")
            return None


    # --- Адаптація trigger/limit ціни до поточної ціни тимчасово вимкнена ---
    # original_bullish_trigger = bullish_group.trigger_price
    # original_bearish_trigger = bearish_group.trigger_price

    # # Для BUY STOP: має бути вище поточної ціни
    # if current_price >= bullish_group.trigger_price:
    #     new_trigger = round(current_price * 1.02, 4)  # +2% від ринку
    #     bullish_group.trigger_price = new_trigger
    #     if bullish_group.limit_price:
    #         bullish_group.limit_price = round(new_trigger * 1.003, 4)  # +0.3%
    #     self.logger.warning(
    #         "BUY STOP адаптовано: %s -> %s (поточна ціна: %s)",
    #         original_bullish_trigger, new_trigger, current_price
    #     )
    #     self.notifier.send_message(
    #         f"⚠️ BUY STOP адаптовано для {asset.symbol}\n"
    #         f"Було: {original_bullish_trigger}\n"
    #         f"Стало: {new_trigger}\n"
    #         f"Поточна ціна: {current_price}",
    #         level="warning"
    #     )

    # # Для SELL STOP: має бути нижче поточної ціни
    # if current_price <= bearish_group.trigger_price:
    #     new_trigger = round(current_price * 0.98, 4)  # -2% від ринку
    #     bearish_group.trigger_price = new_trigger
    #     if bearish_group.limit_price:
    #         bearish_group.limit_price = round(new_trigger * 0.997, 4)  # -0.3%
    #     self.logger.warning(
    #         "SELL STOP адаптовано: %s -> %s (поточна ціна: %s)",
    #         original_bearish_trigger, new_trigger, current_price
    #     )
    #     self.notifier.send_message(
    #         f"⚠️ SELL STOP адаптовано для {asset.symbol}\n"
    #         f"Було: {original_bearish_trigger}\n"
    #         f"Стало: {new_trigger}\n"
    #         f"Поточна ціна: {current_price}",
    #         level="warning"
    #     )

        # Адаптуємо стоп-лоси відповідно до нових цін входу
    # if bullish_group.trigger_price != original_bullish_trigger:
    #     # Зберігаємо відстань стоп-лосу (650 пунктів в оригіналі)
    #     sl_distance = original_bullish_trigger - bullish_group.stop_loss
    #     bullish_group.stop_loss = bullish_group.trigger_price - sl_distance
    #     self.logger.info(
    #         "Оновлено SL для BUY: %s", bullish_group.stop_loss
    #     )

    # if bearish_group.trigger_price != original_bearish_trigger:
    #     # Зберігаємо відстань стоп-лосу (600 пунктів в оригіналі)
    #     sl_distance = bearish_group.stop_loss - original_bearish_trigger
    #     bearish_group.stop_loss = bearish_group.trigger_price + sl_distance
    #     self.logger.info(
    #         "Оновлено SL для SELL: %s", bearish_group.stop_loss
    #     )

        # Розраховуємо розмір для обох напрямків
        buy_quantity = self.risk_manager.calculate_position_size(
            asset, bullish_group
        )
        sell_quantity = self.risk_manager.calculate_position_size(
            asset, bearish_group
        )

        if (buy_quantity is None or buy_quantity <= 0) or \
           (sell_quantity is None or sell_quantity <= 0):
            self.logger.error(
                "Неможливо розрахувати коректний розмір позиції для "
                "OCO %s. Перевірте налаштування плану.", asset.symbol
            )
            return

        # Визначення параметрів для ордерів згідно з планом
        buy_params = {"stopPrice": bullish_group.trigger_price}
        buy_order_type = "STOP_MARKET"
        if "LIMIT" in bullish_group.order_type.upper():
            buy_order_type = "STOP"  # Для Binance Futures API
            if bullish_group.limit_price is not None:
                buy_params["price"] = bullish_group.limit_price

        buy_order = None
        for attempt in range(3):
            try:
                buy_order = self.exchange.place_order(
                    symbol=asset.symbol, side="BUY",
                    order_type=buy_order_type,
                    quantity=buy_quantity, **buy_params
                )
                if buy_order:
                    self.logger.info(
                        "Успішно розміщено BUY STOP для OCO: %s", buy_order
                    )
                    break
            except (BinanceAPIException, BinanceRequestException) as e:
                self.logger.error(
                    "Спроба %d: Помилка розміщення BUY STOP для OCO %s: %s",
                    attempt + 1, asset.symbol, e
                )
                time.sleep(1)

        if not buy_order:
            self.logger.critical(
                "Не вдалося розмістити BUY STOP для OCO пари %s після "
                "декількох спроб.", asset.symbol
            )
            self.notifier.send_message(
                f"Критична помилка: не вдалося розмістити BUY STOP для "
                f"{asset.symbol}", level="critical"
            )
            return

        sell_params = {"stopPrice": bearish_group.trigger_price}
        sell_order_type = "STOP_MARKET"
        if "LIMIT" in bearish_group.order_type.upper():
            sell_order_type = "STOP"  # Для Binance Futures API
            if bearish_group.limit_price is not None:
                sell_params["price"] = bearish_group.limit_price

        sell_order = None
        for attempt in range(3):
            try:
                sell_order = self.exchange.place_order(
                    symbol=asset.symbol, side="SELL",
                    order_type=sell_order_type,
                    quantity=sell_quantity, **sell_params
                )
                if sell_order:
                    self.logger.info(
                        "Успішно розміщено SELL STOP для OCO: %s", sell_order
                    )
                    break
            except (BinanceAPIException, BinanceRequestException) as e:
                self.logger.error(
                    "Спроба %d: Помилка розміщення SELL STOP для OCO %s: %s",
                    attempt + 1, asset.symbol, e
                )
                time.sleep(1)

        if not sell_order:
            self.logger.error(
                "Не вдалося розмістити SELL STOP для OCO пари %s. "
                "Скасування BUY STOP.", asset.symbol
            )
            self.exchange.cancel_order(asset.symbol, buy_order['orderId'])
            return

        self.oco_orders[asset.symbol] = {
            'buy_order_id': buy_order['orderId'],
            'sell_order_id': sell_order['orderId'],
            'is_active': True
        }
        self.logger.info(
            "OCO пара успішно розміщена для %s: BUY ID %s, SELL ID %s",
            asset.symbol, buy_order['orderId'], sell_order['orderId']
        )
        self.notifier.send_message(
            f"OCO ордер розміщено для {asset.symbol}\n"
            f"BUY STOP: {bullish_group.trigger_price}\n"
            f"SELL STOP: {bearish_group.trigger_price}",
            level="trade"
        )

    def _monitor_oco_orders(self):
        """Перевіряє стан активних OCO-пар."""
        if not self.oco_orders:
            return

        try:
            symbols_to_remove = []
            for symbol, oco_info in list(self.oco_orders.items()):
                if not oco_info['is_active']:
                    continue

                try:
                    open_orders = self.exchange.get_open_orders(symbol)
                    open_order_ids = {o['orderId'] for o in open_orders}
                    buy_active = oco_info['buy_order_id'] in open_order_ids
                    sell_active = oco_info['sell_order_id'] in open_order_ids
                except Exception as e:
                    self.logger.warning(
                        f"Не вдалося перевірити ордери для {symbol}: {e}"
                    )
                    continue  # Пропускаємо цей символ

                try:
                    if buy_active and not sell_active:
                        self.logger.info(
                            "SELL частина OCO для %s спрацювала або скасована. "
                            "Скасування BUY частини.", symbol
                        )
                        self.exchange.cancel_order(
                            symbol, oco_info['buy_order_id']
                        )
                        symbols_to_remove.append(symbol)
                    elif not buy_active and sell_active:
                        self.logger.info(
                            "BUY частина OCO для %s спрацювала або скасована. "
                            "Скасування SELL частини.", symbol
                        )
                        self.exchange.cancel_order(
                            symbol, oco_info['sell_order_id']
                        )
                        symbols_to_remove.append(symbol)
                    elif not buy_active and not sell_active:
                        self.logger.info(
                            "Обидві частини OCO для %s неактивні.", symbol
                        )
                        symbols_to_remove.append(symbol)

                except Exception as e:
                    self.logger.error(
                        "Помилка при моніторингу OCO для %s: %s", symbol, e
                    )

            for symbol in symbols_to_remove:
                if symbol in self.oco_orders:
                    del self.oco_orders[symbol]

        except Exception as e:
            self.logger.warning(
                f"Загальна помилка при моніторингу OCO ордерів: {e}"
            )

    def _manage_open_positions(self):
        """Керує відкритими позиціями: встановлює SL/TP, трейлінг-стопи."""
        if not self.plan or not self.risk_manager:
            return

        try:
            positions = self.exchange.get_position_information()
            if not positions:
                return
        except Exception as e:
            self.logger.warning(
                f"Не вдалося отримати інформацію про позиції: {e}"
            )
            return

        open_positions = {
            p['symbol']: p for p in positions if float(p['positionAmt']) != 0
        }
        for symbol, position_data in open_positions.items():
            # Перевіряємо, чи це не хеджувальна позиція (безпечно)
            is_hedge_position = False
            for asset in self.plan.active_assets:
                if asset.hedge and symbol == asset.hedge.symbol:
                    is_hedge_position = True
                    break
            if is_hedge_position:
                continue

            asset_plan = next(
                (a for a in self.plan.active_assets if a.symbol == symbol),
                None
            )
            if not asset_plan:
                continue

            if symbol not in self.managed_positions:
                self.logger.info(
                    "Виявлено нову основну позицію для %s.", symbol
                )
                self.notifier.send_message(
                    f"Відкрито нову позицію: {symbol}\n"
                    f"Ціна входу: {position_data['entryPrice']}\n"
                    f"Розмір: {position_data['positionAmt']}",
                    level="trade"
                )
                self.managed_positions[symbol] = {
                    'trailing_stop_order_id': None,
                    'monitoring_triggers': set(),
                    'last_oi': None,
                    'hedge_info': None
                }
                self._place_initial_sl_tp(position_data, asset_plan)
                # Безпечно відкриваємо хедж тільки якщо він є в плані
                if hasattr(asset_plan, 'hedge') and asset_plan.hedge and \
                   not self.managed_positions[symbol].get('hedge_info'):
                    try:
                        self.logger.info(
                            "Відкриваю хеджувальну позицію для %s: %s",
                            symbol, asset_plan.hedge.symbol
                        )
                        hedge_result = self.risk_manager.open_hedge_position(
                            position_data, asset_plan.hedge
                        )
                        if hedge_result:
                            self.logger.info(
                                "Хеджувальна позиція %s успішно відкрита.",
                                asset_plan.hedge.symbol
                            )
                            self.managed_positions[symbol]['hedge_info'] = {
                                'symbol': asset_plan.hedge.symbol,
                                'active': True
                            }
                        else:
                            self.logger.error(
                                "Не вдалося відкрити хеджувальну позицію %s.",
                                asset_plan.hedge.symbol
                            )
                    except (
                        ValueError, BinanceAPIException,
                        BinanceRequestException
                    ) as e:
                        self.logger.error(
                            "Помилка при відкритті хеджувальної позиції: %s",
                            e
                        )
            else:
                self._update_trailing_stop(position_data, asset_plan)
                self._check_monitoring_rules(position_data, asset_plan)

        closed_symbols = set(self.managed_positions.keys()) - \
            set(open_positions.keys())
        for symbol in closed_symbols:
            self.logger.info("Основна позиція для %s була закрита.", symbol)
            managed_info = self.managed_positions.get(symbol)
            # Безпечно закриваємо хедж якщо він був активний
            if managed_info and managed_info.get(
                'hedge_info', {}
            ).get('active'):
                hedge_symbol = managed_info['hedge_info']['symbol']
                try:
                    self.logger.info(
                        "Закриваю хеджувальну позицію %s, оскільки "
                        "основна позиція %s закрита.",
                        hedge_symbol, symbol
                    )
                    self.risk_manager.close_hedge_position(hedge_symbol)
                    self.logger.info(
                        "Хеджувальна позиція %s успішно закрита.",
                        hedge_symbol
                    )
                except (
                    ValueError, BinanceAPIException, BinanceRequestException
                ) as e:
                    self.logger.error(
                        "Помилка при закритті хеджувальної позиції: %s", e
                    )
            del self.managed_positions[symbol]

    def _handle_shutdown(self):
        self.logger.warning(
            "Ініційовано безпечне завершення роботи. "
            "Закриття всіх позицій."
        )
        self.notifier.send_message(
            "Ініційовано безпечне завершення роботи. "
            "Закриваю всі позиції.", level="warning"
        )
        if self.risk_manager:
            # pylint: disable=protected-access
            self.risk_manager._close_all_positions(keep_hedge=False)

    def _handle_end_of_day_checklist(self):
        """Викликає виконання денного чек-листа."""
        self.logger.info("Ініціація виконання чек-листа на кінець дня.")
        self.notifier.send_message(
            "Починаю виконання чек-листа на кінець дня.", level="info"
        )
        if not self.plan:
            return
        summary = self.journal.get_daily_summary(self.plan.plan_date)
        summary_text = (
            f"Підсумки за {self.plan.plan_date}:\n"
            f"Загальний PnL: ${summary['total_pnl']:.2f}\n"
            f"Всього угод: {summary['total_trades']}\n"
            f"Прибуткових: {summary['winning_trades']}\n"
            f"Збиткових: {summary['losing_trades']}\n"
            f"Win Rate: {summary['win_rate']:.2f}%"
        )
        self.logger.info(summary_text)
        self.notifier.send_message(summary_text, level="success")

    def _check_monitoring_rules(
        self, position: dict, asset_plan: ActiveAsset
    ):
        """Перевіряє правила моніторингу для активної позиції."""
        if not asset_plan.monitoring_rules or not self.risk_manager:
            return
        symbol = position['symbol']
        position_state = self.managed_positions[symbol]

        # Перевірка funding rate
        funding_rule = asset_plan.monitoring_rules.get('funding_rate_pct')
        if funding_rule and 'funding_rate' not in \
                position_state['monitoring_triggers']:
            market_data = self.exchange.get_funding_rate_and_mark_price(
                symbol
            )
            if market_data:
                funding_rate_pct = market_data['lastFundingRate'] * 100
                threshold = (
                    funding_rule.threshold or
                    funding_rule.threshold_pct or 0
                )
                if abs(funding_rate_pct) >= threshold:
                    self.logger.warning(
                        "FUNDING RATE TRIGGER для %s! Поточний: %.4f%%, "
                        "Поріг: %s%%",
                        symbol, funding_rate_pct, threshold
                    )
                    self.risk_manager.handle_monitoring_action(
                        funding_rule.action, position, asset_plan
                    )
                    position_state['monitoring_triggers'].add('funding_rate')

        # Перевірка open interest
        oi_rule = asset_plan.monitoring_rules.get('open_interest_pct')
        if oi_rule and 'open_interest' not in \
                position_state['monitoring_triggers']:
            oi_data = self.exchange.get_open_interest_stats(symbol)
            if not oi_data:
                return

            current_oi = oi_data.get('openInterest')
            if current_oi is None:
                return

            try:
                current_oi_float = float(current_oi)
            except (ValueError, TypeError):
                self.logger.error(
                    "Не вдалося перетворити OI '%s' у float для %s",
                    current_oi, symbol
                )
                return

            last_oi = position_state.get('last_oi')
            position_state['last_oi'] = current_oi_float

            if last_oi is not None:
                oi_change_pct = (
                    (current_oi_float - last_oi) / last_oi
                ) * 100
                threshold = (
                    oi_rule.threshold or oi_rule.threshold_pct or 0
                )
                if abs(oi_change_pct) >= threshold:
                    self.logger.warning(
                        "OPEN INTEREST TRIGGER для %s! "
                        "Зміна OI: %.2f%%, Поріг: %s%%",
                        symbol, oi_change_pct, threshold
                    )
                    self.risk_manager.handle_monitoring_action(
                        oi_rule.action, position, asset_plan
                    )
                    position_state['monitoring_triggers'].add(
                        'open_interest'
                    )

    def _place_initial_sl_tp(self, position: dict, asset_plan: ActiveAsset):
        """Розміщує початкові Stop Loss та Take Profit ордери."""
        symbol = position['symbol']
        position_amount = float(position['positionAmt'])
        side_to_close = "SELL" if position_amount > 0 else "BUY"
        order_group_name = "bullish" if position_amount > 0 else "bearish"
        order_group = asset_plan.order_groups.get(order_group_name)
        if not order_group:
            return
        # Free-Margin Guard
        if not self._should_place_new_orders():
            self.logger.warning(f"Free-Margin Guard: SL/TP для {symbol} не буде розміщено.")
            return
        # Динамічний SL через ATR
        interval = "1h"
        klines = self.exchange.get_historical_klines(symbol, interval)
        atr = None
        if klines:
            atr = calculate_atr(klines, length=14)
        if atr and atr > 0:
            sl_distance = atr * 1.5
            entry = float(position['entryPrice'])
            sl_price = entry - sl_distance if side_to_close == "SELL" else entry + sl_distance
            self.logger.info(f"Динамічний SL для {symbol}: ATR={atr:.2f}, SL={sl_price:.2f}")
        else:
            sl_price = order_group.stop_loss
            self.logger.info(f"Статичний SL для {symbol}: SL={sl_price}")
        if sl_price is None:
            self.logger.error(
                "Ціна Stop Loss не визначена для %s в групі %s",
                symbol, order_group_name
            )
            return

        sl_order = None
        for attempt in range(3):
            try:
                sl_order = self.exchange.place_order(
                    symbol=symbol, side=side_to_close,
                    order_type="STOP_MARKET",
                    quantity=abs(position_amount), stopPrice=sl_price,
                    reduceOnly=True
                )
                if sl_order:
                    self.logger.info(
                        "Успішно розміщено початковий SL для %s: %s",
                        symbol, sl_order
                    )
                    break
            except (BinanceAPIException, BinanceRequestException) as e:
                self.logger.error(
                    "Спроба %d: Помилка розміщення SL для %s: %s",
                    attempt + 1, symbol, e
                )
                time.sleep(1)

        if sl_order and symbol in self.managed_positions:
            self.managed_positions[symbol]['trailing_stop_order_id'] = \
                sl_order['orderId']

    def _update_trailing_stop(self, position: dict, asset_plan: ActiveAsset):
        """Оновлює трейлінг-стоп для позиції."""
        dm_config = asset_plan.dynamic_management
        if not dm_config or not dm_config.trailing_sl_atr_multiple:
            return
        symbol = position['symbol']
        sl_order_id = self.managed_positions.get(symbol, {}).get(
            'trailing_stop_order_id'
        )
        if not sl_order_id:
            self.logger.debug("Немає SL ордера для трейлінгу %s.", symbol)
            return
        entry_price = float(position['entryPrice'])
        position_amount = float(position['positionAmt'])
        is_long = position_amount > 0
        current_price = self.exchange.get_current_price(symbol)
        if not current_price:
            return
        profit_from_entry = (current_price - entry_price) if is_long \
            else (entry_price - current_price)
        activate_after_profit = dm_config.activate_after_profit or 0
        if profit_from_entry < activate_after_profit:
            return
        interval = f"{dm_config.atr_window_min}m"
        klines = self.exchange.get_historical_klines(symbol, interval)
        if not klines:
            self.logger.warning(
                "Не вдалося отримати klines для розрахунку ATR для %s.",
                symbol
            )
            return

        atr_value = calculate_atr(klines, length=14)
        if not atr_value or atr_value <= 0:
            self.logger.warning(
                "Некоректне значення ATR (%s) для %s. "
                "Оновлення SL пропущено.", atr_value, symbol
            )
            return

        new_sl_price = (
            current_price - (atr_value * dm_config.trailing_sl_atr_multiple)
            if is_long else
            current_price + (atr_value * dm_config.trailing_sl_atr_multiple)
        )
        if new_sl_price is None:
            return

        open_orders = self.exchange.get_open_orders(symbol)
        current_sl_order = next(
            (o for o in open_orders if o['orderId'] == sl_order_id), None
        )
        if not current_sl_order:
            self.logger.warning(
                "Не знайдено активний SL ордер (%s) для %s, "
                "можливо він спрацював.", sl_order_id, symbol
            )
            if symbol in self.managed_positions and \
               'trailing_stop_order_id' in self.managed_positions[symbol]:
                del self.managed_positions[symbol]['trailing_stop_order_id']
            return
        current_sl_price = float(current_sl_order['stopPrice'])
        should_move_stop = (is_long and new_sl_price > current_sl_price) or \
                           (not is_long and new_sl_price < current_sl_price)
        if should_move_stop:
            self.logger.info(
                "ТРЕЙЛІНГ-СТОП: Переміщення SL для %s з %s на %.4f",
                symbol, current_sl_price, new_sl_price
            )
            side_to_close = "SELL" if is_long else "BUY"
            new_order = None
            for attempt in range(3):
                try:
                    new_order = self.exchange.cancel_and_replace_order(
                        symbol=symbol, cancel_order_id=sl_order_id,
                        side=side_to_close, order_type="STOP_MARKET",
                        quantity=abs(position_amount),
                        stopPrice=round(new_sl_price, 4),
                        reduceOnly=True
                    )
                    if new_order:
                        self.logger.info(
                            "Успішно оновлено SL для %s: %s", symbol, new_order
                        )
                        break
                except (BinanceAPIException, BinanceRequestException) as e:
                    self.logger.error(
                        "Спроба %d: Помилка оновлення SL для %s: %s",
                        attempt + 1, symbol, e
                    )
                    time.sleep(1)

            if new_order:
                self.managed_positions[symbol]['trailing_stop_order_id'] = \
                    new_order['orderId']

    def _handle_cancel_all_untriggered(self):
        """Скасовує всі неактивовані ордери для активних ассетів."""
        if not self.plan:
            return
        for asset in self.plan.active_assets:
            open_orders = self.exchange.get_open_orders(symbol=asset.symbol)
            if not open_orders:
                continue
            for order in open_orders:
                self.exchange.cancel_order(
                    symbol=asset.symbol, order_id=order['orderId']
                )

    def _handle_close_all_open_positions(self):
        """Закриває всі відкриті позиції при завершенні торгової сесії."""
        try:
            positions = self.exchange.get_open_positions()
            if not positions:
                self.logger.info("Немає відкритих позицій для закриття.")
                return
            
            closed_count = 0
            for position in positions:
                if float(position['positionAmt']) != 0:
                    symbol = position['symbol']
                    size = abs(float(position['positionAmt']))
                    side = 'SELL' if float(position['positionAmt']) > 0 else 'BUY'
                    
                    try:
                        result = self.exchange.place_market_order(symbol, side, size)
                        if result:
                            self.logger.info(f"Закрито позицію {symbol}: {side} {size}")
                            closed_count += 1
                    except Exception as e:
                        self.logger.error(f"Помилка закриття позиції {symbol}: {e}")
            
            if closed_count > 0:
                self.notifier.send_message(
                    f"🔚 Завершення торгів: закрито {closed_count} позицій",
                    level="info"
                )
                self.logger.info(f"Успішно закрито {closed_count} позицій при завершенні торгів.")
            
        except Exception as e:
            self.logger.error(f"Помилка при закритті позицій: {e}")
            self.notifier.send_message(
                f"❌ Помилка закриття позицій: {e}",
                level="error"
            )

    def _handle_unknown_action(self):
        """Обробляє невідому дію з торгового плану."""
        self.logger.warning("Спроба виконати невідому дію з торгового плану.")

    def _handle_close_all_positions(self):
        """Закриває всі відкриті позиції."""
        self.logger.info("Закриття всіх відкритих позицій...")
        try:
            positions = self.exchange.get_open_positions()
            if not positions:
                self.logger.info("Немає відкритих позицій для закриття")
                return

            for position in positions:
                symbol = position.get('symbol')
                size = float(position.get('positionAmt', 0))
                if size != 0:
                    side = 'SELL' if size > 0 else 'BUY'
                    quantity = abs(size)
                    
                    # Закриваємо позицію ринковим ордером
                    result = self.exchange.place_market_order(
                        symbol=symbol,
                        side=side,
                        quantity=quantity
                    )
                    
                    if result:
                        self.logger.info(
                            "Позицію %s закрито: %s %.6f", 
                            symbol, side, quantity
                        )
                        self.notifier.send_message(
                            f"✅ Позицію {symbol} закрито: {side} {quantity}",
                            level="info"
                        )
                    else:
                        self.logger.error("Не вдалося закрити позицію %s", symbol)
            
            self.notifier.send_message("🔚 Усі позиції закрито", level="success")
            
        except Exception as e:
            self.logger.error("Помилка закриття позицій: %s", e)
            self.notifier.send_message(
                f"❌ Помилка закриття позицій: {e}",
                level="error"
            )

    def _handle_verify_conditions(self):
        """Перевіряє умови перед макро."""
        self.logger.info("Перевірка умов перед макро...")
        # Тут можна додати логіку перевірки ринкових умов
        self.notifier.send_message("✅ Умови перед макро перевірені", level="info")

    def _handle_monitor_jobless_claims(self):
        """Моніторить реліз Jobless Claims."""
        self.logger.info("Моніторинг Jobless Claims...")
        # Тут можна додати логіку отримання макро-даних
        self.notifier.send_message("📊 Моніторинг Jobless Claims активний", level="info")

    def _handle_place_conditional_orders(self):
        """Розміщує умовні ордери."""
        self.logger.info("Розміщення умовних ордерів...")
        self._handle_place_all_orders()
        
    def _handle_check_arb_conditions(self):
        """Перевіряє умови для ARB."""
        self.logger.info("Перевірка умов для ARB...")
        # Тут можна додати логіку перевірки BTC dominance
        self.notifier.send_message("🔍 Умови ARB перевірені", level="info")
        
    def _handle_check_sol_entry(self):
        """Перевіряє умови входу для SOL."""
        self.logger.info("Перевірка умов входу для SOL...")
        # Тут можна додати логіку активації SOL позицій
        self.notifier.send_message("⚡ Умови SOL перевірені", level="info")

    def _check_global_risks(self, _: datetime):
        """
        Kill-switch: якщо денний PnL ≤ emergency_stop_loss,
        закрити всі позиції та поставити паузу.
        Flash-drop: стара логіка.
        """
        if not self.plan or not self.risk_manager:
            return

        try:
            # Kill-switch — порівнюємо PnL у USD із порогом у USD (equity * emergency_sl)
            emergency_sl_ratio = self.plan.global_settings.emergency_stop_loss
            today = self.plan.plan_date
            daily_pnl_usd = self.journal.get_daily_pnl(today)
            # Оновлюємо equity, якщо ще не ініціалізовано
            if self.risk_manager and (not getattr(self.risk_manager, 'equity', 0)):
                self.risk_manager.update_equity()
            equity = getattr(self.risk_manager, 'equity', 0.0) or 0.0
            threshold_usd = equity * emergency_sl_ratio if equity else None
            if (
                daily_pnl_usd is not None and threshold_usd is not None and
                daily_pnl_usd <= threshold_usd
            ):
                self.logger.critical(
                    f"Kill-switch: денний PnL ${daily_pnl_usd:.2f} ≤ "
                    f"поріг ${threshold_usd:.2f}. Торги призупинено."
                )
                self.risk_manager._close_all_positions(
                    reason="Kill-switch"
                )
                self._pause_trading()
                return
        except Exception as e:
            self.logger.warning(
                f"Помилка при перевірці kill-switch: {e}"
            )

        # Time-stop 23:00 EEST — закрити всі відкриті позиції, однократно на дату плану
        try:
            local_tz = pytz.timezone('Europe/Kiev')
            now_local = datetime.now(pytz.utc).astimezone(local_tz)
            if now_local.hour >= 23:
                # не повторюємо для тієї ж дати
                if getattr(self, '_time_stop_enforced_date', None) != now_local.date():
                    self.logger.warning("Time-stop: 23:00 EEST досягнуто — закриваємо всі позиції")
                    self._handle_close_all_open_positions()
                    self._time_stop_enforced_date = now_local.date()
        except Exception as e:
            self.logger.debug(f"Помилка перевірки time-stop: {e}")

        # Перевірка волатільності BTC
        try:
            if self._check_btc_volatility_simple():
                self.logger.warning("🚨 Скасовуємо ордери через високу волатільність BTC!")
                self._cancel_all_orders()
        except Exception as e:
            self.logger.debug(f"Помилка перевірки волатільності: {e}")

    def _pause_trading(self):
        """Призупиняє торги."""
        self.trading_paused = True
        self.logger.critical("Trading PAUSED - всі торгові операції зупинено")
        if hasattr(self, 'notifier') and self.notifier:
            self.notifier.send_message(
                "🛑 ТОРГИ ПРИЗУПИНЕНО",
                level="critical"
            )
        # Flash-drop
        if not self.plan:
            return
        for trigger_name, trigger_details in self.plan.risk_triggers.items():
            if trigger_name == "btc_flash_drop":
                assets_to_check = trigger_details.assets or []
                for symbol in assets_to_check:
                    current_price = self.exchange.get_current_price(symbol)
                    if current_price is None:
                        continue
                    last_price = self.price_tracker.get(symbol)
                    self.price_tracker[symbol] = current_price
                    if last_price:
                        price_drop_pct = (
                            (last_price - current_price) / last_price * 100
                        )
                        self.logger.debug(
                            "Перевірка Flash Drop для %s: Поточна ціна: %s, "
                            "Попередня: %s, Падіння: %.4f%%",
                            symbol, current_price, last_price, price_drop_pct
                        )
                        if price_drop_pct >= trigger_details.threshold_pct:
                            self.logger.warning(
                                "!!! FLASH DROP DETECTED для %s: %.2f%% !!!",
                                symbol, price_drop_pct
                            )
                            if self.risk_manager:
                                self.risk_manager.execute_risk_action(
                                    trigger_details.action
                                )

    def _check_btc_volatility_simple(self) -> bool:
        """
        Простий синхронний варіант перевірки волатільності BTC.
        Використовує лише поточну ціну для швидкої оцінки.
        """
        try:
            # Перевіряємо не частіше ніж раз на хвилину
            now = datetime.now(pytz.utc)
            if (self.last_volatility_check and 
                now - self.last_volatility_check < timedelta(minutes=1)):
                return False
            
            # Отримуємо поточну ціну BTC
            btc_price = self.exchange.get_current_price('BTCUSDT')
            if not btc_price:
                return False
            
            # Зберігаємо історію цін для розрахунку волатільності
            if not hasattr(self, 'btc_price_history'):
                self.btc_price_history = []
            
            self.btc_price_history.append({
                'price': btc_price,
                'time': now
            })
            
            # Тримаємо останні 10 записів (останні 10 хвилин)
            self.btc_price_history = self.btc_price_history[-10:]
            
            # Якщо маємо достатньо даних, розраховуємо волатільність
            if len(self.btc_price_history) >= 5:
                prices = [p['price'] for p in self.btc_price_history]
                
                # Прості розрахунки returns та std dev
                returns = []
                for i in range(1, len(prices)):
                    ret = (prices[i] - prices[i-1]) / prices[i-1]
                    returns.append(ret)
                
                if returns:
                    # Середнє та стандартне відхилення
                    mean_return = sum(returns) / len(returns)
                    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
                    volatility = (variance ** 0.5) * 100  # В відсотках
                    
                    self.last_volatility_check = now
                    
                    self.logger.debug(f"BTC простий розрахунок волатільності: {volatility:.2f}%")
                    
                    if volatility > 3.0:
                        self.logger.warning(
                            f"🚨 ВИСОКА ВОЛАТІЛЬНІСТЬ BTC: {volatility:.2f}% > 3%"
                        )
                        return True
                        
        except Exception as e:
            self.logger.error(f"Помилка простої перевірки волатільності BTC: {e}")
            
        return False

    def _cancel_all_orders(self):
        """Скасовує всі активні ордери для всіх активів"""
        try:
            if not self.plan:
                return
                
            cancelled_count = 0
            for asset in self.plan.active_assets:
                open_orders = self.exchange.get_open_orders(symbol=asset.symbol)
                if not open_orders:
                    continue
                    
                for order in open_orders:
                    try:
                        self.exchange.cancel_order(
                            symbol=asset.symbol, 
                            order_id=order['orderId']
                        )
                        cancelled_count += 1
                        self.logger.info(
                            f"Скасовано ордер {order['orderId']} для {asset.symbol}"
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Помилка скасування ордера {order['orderId']}: {e}"
                        )
            
            if cancelled_count > 0:
                self.logger.warning(f"📝 Скасовано {cancelled_count} ордерів через волатільність BTC")
                self.notifier.send_message(
                    f"🚨 Скасовано {cancelled_count} ордерів через високу волатільність BTC",
                    level="warning"
                )
                
        except Exception as e:
            self.logger.error(f"Помилка при скасуванні ордерів: {e}")
