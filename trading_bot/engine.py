# trading_bot/engine.py
# Основний рушій, який виконує торговий план.
"""Основной рушій, який виконує торговий план."""

import logging
import time
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
        self.executed_phases = set()
        self.managed_positions = {}
        self.oco_orders = {}
        self.price_tracker = {}
        self.last_check_time = datetime.now(pytz.utc)

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
        if not self.plan:
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

            if current_utc_time.strftime('%Y-%m-%d %H:%M') == \
               phase_utc_time.strftime('%Y-%m-%d %H:%M'):
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
        for asset in self.plan.active_assets:
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
        """Розміщує два протилежні STOP ордери для імітації OCO-пробою."""
        bullish_group = asset.order_groups.get("bullish")
        bearish_group = asset.order_groups.get("bearish")
        if not bullish_group or not bearish_group:
            self.logger.error(
                "Для OCO стратегії потрібні обидві групи ордерів "
                "(bullish/bearish) для %s", asset.symbol
            )
            return

        if not self.risk_manager:
            return

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

        buy_order = self.exchange.place_order(
            symbol=asset.symbol, side="BUY", order_type=buy_order_type,
            quantity=buy_quantity, **buy_params
        )
        if not buy_order:
            self.logger.error(
                "Не вдалося розмістити BUY STOP для OCO пари %s",
                asset.symbol
            )
            return

        sell_params = {"stopPrice": bearish_group.trigger_price}
        sell_order_type = "STOP_MARKET"
        if "LIMIT" in bearish_group.order_type.upper():
            sell_order_type = "STOP"  # Для Binance Futures API
            if bearish_group.limit_price is not None:
                sell_params["price"] = bearish_group.limit_price

        sell_order = self.exchange.place_order(
            symbol=asset.symbol, side="SELL", order_type=sell_order_type,
            quantity=sell_quantity, **sell_params
        )
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
        symbols_to_remove = []
        for symbol, oco_info in list(self.oco_orders.items()):
            if not oco_info['is_active']:
                continue

            try:
                open_orders = self.exchange.get_open_orders(symbol)
                open_order_ids = {o['orderId'] for o in open_orders}
                buy_active = oco_info['buy_order_id'] in open_order_ids
                sell_active = oco_info['sell_order_id'] in open_order_ids

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

            except (BinanceAPIException, BinanceRequestException) as e:
                self.logger.error(
                    "Помилка при моніторингу OCO для %s: %s", symbol, e
                )

        for symbol in symbols_to_remove:
            if symbol in self.oco_orders:
                del self.oco_orders[symbol]

    def _manage_open_positions(self):
        """Керує відкритими позиціями: встановлює SL/TP, трейлінг-стопи."""
        if not self.plan or not self.risk_manager:
            return
        positions = self.exchange.get_position_information()
        if not positions:
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
                    f"Ціна входу: {position_data['entryPrice']}",
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
                            "Відкриваю хеджувальну позицію для %s", symbol
                        )
                        self.risk_manager.open_hedge_position(
                            position_data, asset_plan.hedge
                        )
                        self.managed_positions[symbol]['hedge_info'] = {
                            'symbol': asset_plan.hedge.symbol, 'active': True
                        }
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
                        "Закриваю хеджувальну позицію %s", hedge_symbol
                    )
                    self.risk_manager.close_hedge_position(hedge_symbol)
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
            self.risk_manager._close_all_long_positions(keep_hedge=False)

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
        sl_price = order_group.stop_loss
        if sl_price is None:
            self.logger.error(
                "Ціна Stop Loss не визначена для %s в групі %s",
                symbol, order_group_name
            )
            return

        sl_order = self.exchange.place_order(
            symbol=symbol, side=side_to_close, order_type="STOP_MARKET",
            quantity=abs(position_amount), stopPrice=sl_price,
            reduceOnly=True
        )
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
        atr_value = calculate_atr(klines, length=14)
        if not atr_value:
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
            new_order = self.exchange.cancel_and_replace_order(
                symbol=symbol, cancel_order_id=sl_order_id,
                side=side_to_close, order_type="STOP_MARKET",
                quantity=abs(position_amount),
                stopPrice=round(new_sl_price, 4),
                reduceOnly=True
            )
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

    def _handle_unknown_action(self):
        """Обробляє невідому дію з торгового плану."""
        self.logger.warning("Спроба виконати невідому дію з торгового плану.")

    def _check_global_risks(self, _: datetime):
        """Перевіряє глобальні ризики, такі як раптові падіння цін."""
        if not self.plan or not self.risk_manager:
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
                        if price_drop_pct >= trigger_details.threshold_pct:
                            self.logger.warning(
                                "!!! FLASH DROP DETECTED для %s: %.2f%% !!!",
                                symbol, price_drop_pct
                            )
                            self.risk_manager.execute_risk_action(
                                trigger_details.action
                            )
