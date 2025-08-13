# trading_bot/exchange_connector.py
# Цей модуль інкапсулює всю логіку взаємодії з API Binance Futures.
"""Інкапсулює логіку для взаємодії з API Binance Futures."""

import logging
from typing import Optional
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from binance.helpers import round_step_size
import requests.exceptions
from tenacity import (
    retry, stop_after_attempt, wait_exponential, retry_if_exception_type
)
from decimal import Decimal, ROUND_DOWN


class BinanceFuturesConnector:
    """
    Клас для взаємодії з Binance Futures API.
    Надає методи для перевірки з'єднання, отримання даних та розміщення ордерів.
    """
    # --- Декоратор retry для всіх критичних API-запитів ---
    @staticmethod
    def _retry_on_api_error():
        return retry(
            reraise=True,
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((
                BinanceAPIException, BinanceRequestException,
                ConnectionError, TimeoutError,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectTimeout,
                requests.exceptions.ConnectionError
            ))
        )

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        self.testnet = testnet
        try:
            self.client = Client(api_key, api_secret, testnet=self.testnet)
            self.client.API_URL = (
                self.client.FUTURES_URL if not testnet
                else self.client.FUTURES_TESTNET_URL
            )
            logging.info(
                "Binance Futures Connector ініціалізовано. Режим Testnet: %s",
                self.testnet
            )
        except Exception as e:
            logging.critical(
                "Помилка ініціалізації клієнта Binance: %s", e, exc_info=True
            )
            raise

    @_retry_on_api_error()
    def get_exchange_filters(self, symbol: str) -> dict:
        """
        Отримує фільтри (правила) для торгової пари з біржі.
        Цей метод інкапсулює логіку отримання фільтрів.
        """
        try:
            info = self.client.futures_exchange_info()
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    filters = {f['filterType']: f for f in s['filters']}
                    return filters
        except (BinanceAPIException, BinanceRequestException) as e:
            logging.error("Не вдалося отримати фільтри для %s: %s", symbol, e)
        return {}

    def round_price(self, price: float, tick_size: str) -> str:
        """Round price to allowed tick size as string (Binance prefers str)."""
        d_price = Decimal(str(price))
        d_tick = Decimal(str(tick_size))
        return str(d_price.quantize(d_tick, rounding=ROUND_DOWN))

    def format_quantity_and_price(self, symbol: str, quantity: float,
                                 price: Optional[float] = None, stop_price: Optional[float] = None,
                                 side: Optional[str] = None, order_type: Optional[str] = None) -> dict:
        """
        Форматує quantity, price та stopPrice згідно з фільтрами біржі.
        Повертає словник із відформатованими значеннями.
        """
        filters = self.get_exchange_filters(symbol)
        result = {}
        
        # Форматування quantity
        if 'LOT_SIZE' in filters:
            step_size = filters['LOT_SIZE']['stepSize']
            result['quantity'] = round_step_size(quantity, step_size)
        else:
            result['quantity'] = quantity

        # Форматування price/stopPrice з урахуванням тик-сайза та напряму для STOP
        if 'PRICE_FILTER' in filters:
            tick_size = filters['PRICE_FILTER']['tickSize']
            if stop_price is not None:
                sp = float(stop_price)
                result['stopPrice'] = self.round_price(sp, tick_size)
            if price is not None:
                lp = float(price)
                result['price'] = self.round_price(lp, tick_size)

            # Для STOP (лімітний) гарантуємо, що price на один тик «далі» від stopPrice
            try:
                if order_type and order_type.upper() == 'STOP' and side and 'stopPrice' in result:
                    d_tick = float(tick_size)
                    sp = float(result['stopPrice'])
                    if side.upper() == 'BUY':
                        # price > stopPrice мінімум на 1 тик
                        min_price = sp + d_tick
                        lp = float(result.get('price', min_price))
                        if lp <= sp:
                            lp = min_price
                        result['price'] = self.round_price(lp, tick_size)
                    elif side.upper() == 'SELL':
                        # price < stopPrice мінімум на 1 тик
                        max_price = sp - d_tick
                        lp = float(result.get('price', max_price))
                        if lp >= sp:
                            lp = max_price
                        result['price'] = self.round_price(lp, tick_size)
            except Exception:
                # Безпечний фолбек: лишаємо як є
                pass

        # КРИТИЧНА ПЕРЕВІРКА minNotional з контролем ризику
        if 'MIN_NOTIONAL' in filters:
            min_notional = float(filters['MIN_NOTIONAL']['notional'])
            effective_price = float(price or stop_price or 0)
            if effective_price > 0:
                current_notional = float(result['quantity']) * effective_price
                if current_notional < min_notional:
                    # НЕБЕЗПЕЧНО: НЕ збільшуємо quantity автоматично!
                    # Це може призвести до неконтрольованої ескалації ризику
                    required_qty = min_notional / effective_price * 1.01
                    
                    # Перевіряємо, чи збільшення quantity не перевищує розумні межі
                    qty_increase_factor = required_qty / float(result['quantity'])
                    if qty_increase_factor > 5.0:  # Більше ніж у 5 разів
                        logging.error(
                            "ВІДХИЛЕНО: Quantity для %s потребує збільшення у %.1fx разів "
                            "(з %s до %s) для дотримання minNotional (%s USD). "
                            "Це неприйнятна ескалація ризику! Скасовуємо ордер.",
                            symbol, qty_increase_factor, result['quantity'], 
                            required_qty, min_notional
                        )
                        raise ValueError(f"Неприйнятна ескалація ризику для {symbol}")
                    
                    # Якщо збільшення розумне - застосовуємо
                    if 'LOT_SIZE' in filters:
                        step_size = filters['LOT_SIZE']['stepSize']
                        result['quantity'] = round_step_size(required_qty, step_size)
                    else:
                        result['quantity'] = required_qty
                    logging.warning(
                        "Quantity для %s збільшено до %s для дотримання minNotional (%s USD). "
                        "Збільшення: %.1fx",
                        symbol, result['quantity'], min_notional, qty_increase_factor
                    )

        return result

    def is_symbol_active(self, symbol: str) -> bool:
        """Перевіряє, чи активний символ для торгівлі."""
        try:
            info = self.client.futures_exchange_info()
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    return s['status'] == 'TRADING'
            return False
        except (BinanceAPIException, BinanceRequestException) as e:
            logging.error("Не вдалося перевірити статус символу %s: %s", symbol, e)
            return False

    @_retry_on_api_error()
    def check_connection(self) -> bool:
        """Перевіряє з'єднання з API та валідність ключів."""
        try:
            # Використовуємо найпростіший метод для перевірки
            self.client.futures_exchange_info()
            logging.info("Підключення до Binance API успішне. API ключі валідні.")
            return True
        except (BinanceAPIException, BinanceRequestException) as e:
            logging.error(
                "Помилка API Binance при перевірці з'єднання: %s", e
            )
            return False

    @_retry_on_api_error()
    def get_open_interest_stats(self, symbol: str) -> dict | None:
        """Отримує статистику відкритого інтересу для символу."""
        try:
            data = self.client.futures_open_interest(symbol=symbol)
            return {
                'openInterest': float(data['openInterest']),
                'timestamp': data['timestamp']
            }
        except BinanceAPIException as e:
            logging.error(
                "Не вдалося отримати Open Interest для %s: %s", symbol, e
            )
            return None

    @_retry_on_api_error()
    def get_funding_rate_and_mark_price(self, symbol: str) -> dict | None:
        """Отримує ставку фінансування та маркувальну ціну для символу."""
        try:
            # suppress pylance error if method exists
            method = getattr(self.client, 'futures_premium_index', None)
            if callable(method):
                result = method(symbol=symbol)  # type: ignore
                if isinstance(result, dict) and 'markPrice' in result and 'lastFundingRate' in result:
                    return {
                        'markPrice': float(result['markPrice']),
                        'lastFundingRate': float(result['lastFundingRate'])
                    }
                else:
                    logging.error("Результат futures_premium_index не содержит нужных ключей или не dict")
                    return None
            else:
                logging.error("Метод futures_premium_index не найден в Binance Client")
                return None
        except BinanceAPIException as e:
            logging.error(
                "Не вдалося отримати funding rate для %s: %s", symbol, e
            )
            return None

    def get_historical_klines(self, symbol: str, interval: str, limit: int = 100) -> list:
        """Отримує історичні дані свічок (klines) для символу."""
        try:
            klines = self.client.futures_klines(
                symbol=symbol, interval=interval, limit=limit
            )
            if isinstance(klines, list):
                return klines
            else:
                logging.error("API вернул не список, а %s", type(klines))
                return []
        except BinanceAPIException as e:
            logging.error(
                "Не вдалося отримати klines для %s: %s", symbol, e
            )
            return []

    @_retry_on_api_error()
    def get_account_summary(self, asset: str = 'USDT') -> dict | None:
        """
        Отримує зведену інформацію про рахунок: загальний баланс,
        доступну маржу та PnL.
        """
        try:
            account_info = self.client.futures_account()
            # logging.debug(f"Account Info: {account_info}")

            total_balance = float(account_info['totalWalletBalance'])
            free_margin = float(account_info['availableBalance'])
            total_pnl = float(account_info['totalUnrealizedProfit'])

            # Знаходимо конкретний актив для більш детальної інформації
            asset_details = next(
                (a for a in account_info['assets'] if a['asset'] == asset),
                None
            )
            if asset_details:
                wallet_balance = float(asset_details['walletBalance'])
                unrealized_profit = float(
                    asset_details['unrealizedProfit']
                )
            else:
                wallet_balance = total_balance
                unrealized_profit = total_pnl

            return {
                "total_balance": total_balance,
                "free_margin": free_margin,
                "total_pnl": total_pnl,
                "wallet_balance": wallet_balance,
                "unrealized_profit": unrealized_profit
            }
        except (BinanceAPIException, BinanceRequestException) as e:
            logging.error("Не вдалося отримати зведення по рахунку: %s", e)
            return None

    def get_free_margin(self, asset: str = 'USDT') -> float | None:
        """Отримує доступну маржу для нових ордерів."""
        summary = self.get_account_summary(asset)
        return summary["free_margin"] if summary else None

    def get_total_balance(self, asset: str = 'USDT') -> float | None:
        """Отримує загальний баланс гаманця."""
        summary = self.get_account_summary(asset)
        return summary["total_balance"] if summary else None

    @_retry_on_api_error()
    def get_futures_account_balance(self, asset: str = 'USDT') -> float | None:
        try:
            # Використовуємо futures_account() замість застарілого futures_account_balance()
            account_info = self.client.futures_account() 
            for item in account_info['assets']:
                if item['asset'] == asset:
                    return float(item['availableBalance'])
            logging.warning(
                "Актив %s не знайдено у балансі ф'ючерсного гаманця.", asset
            )
            return 0.0
        except BinanceAPIException as e:
            logging.error(
                "Не вдалося отримати баланс ф'ючерсного гаманця: %s", e
            )
            return None

    @_retry_on_api_error()
    def get_current_price(self, symbol: str) -> float | None:
        """Отримує поточну ринкову ціну для вказаного символу."""
        try:
            ticker = self.client.futures_ticker(symbol=symbol)
            price = float(ticker['lastPrice'])
            
            # КРИТИЧНА ВАЛІДАЦІЯ: запобігаємо нульовим цінам
            if price <= 0:
                logging.error("КРИТИЧНА ПОМИЛКА: отримано нульову або негативну ціну для %s: %s", symbol, price)
                return None
                
            # Додаткова перевірка на розумність ціни
            if price < 1e-10:  # Менше за 0.0000000001
                logging.error("КРИТИЧНА ПОМИЛКА: ціна занадто мала для %s: %s", symbol, price)
                return None
                
            return price
        except BinanceAPIException as e:
            logging.error("Не вдалося отримати ціну для %s: %s", symbol, e)
            return None
        except (ValueError, KeyError) as e:
            logging.error("Помилка парсингу ціни для %s: %s", symbol, e)
            return None

    def _validate_stop_order(
        self, side: str, stop_price: float | None, limit_price: float | None = None
    ):
        """Валідація параметрів STOP ордера перед відправкою на біржу."""
        if stop_price is None:
            raise ValueError("stop_price не може бути None")
        if limit_price is None:
            return  # STOP_MARKET — валідація не потрібна

        if side == "SELL" and limit_price >= stop_price:
            raise ValueError(
                f"SELL STOP-LIMIT: price ({limit_price}) must be < "
                f"stopPrice ({stop_price})"
            )
        if side == "BUY" and limit_price <= stop_price:
            raise ValueError(
                f"BUY STOP-LIMIT: price ({limit_price}) must be > "
                f"stopPrice ({stop_price})"
            )

    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, **kwargs) -> dict | None:
        """Універсальний метод для розміщення ордера з автоматичним форматуванням."""
        try:
            # Отримуємо stopPrice та price з kwargs
            stop_price = kwargs.get('stopPrice')
            price = kwargs.get('price')
            
            # Форматуємо quantity, price та stopPrice згідно з фільтрами
            formatted = self.format_quantity_and_price(
                symbol=symbol,
                quantity=quantity,
                price=price,
                stop_price=stop_price,
                side=side,
                order_type=order_type
            )
            
            # Оновлюємо параметри відформатованими значеннями
            quantity = formatted['quantity']
            if 'price' in formatted:
                kwargs['price'] = formatted['price']
            if 'stopPrice' in formatted:
                kwargs['stopPrice'] = formatted['stopPrice']

            # Валідація STOP ордерів перед відправкою
            if order_type in ["STOP", "STOP_MARKET"] and "stopPrice" in kwargs:
                try:
                    sp_raw = kwargs.get("stopPrice", None)
                    lp_raw = kwargs.get("price", None)
                    stop_price = float(sp_raw) if sp_raw is not None else None
                    limit_price = float(lp_raw) if lp_raw is not None else None
                except (TypeError, ValueError):
                    raise ValueError("stopPrice/price повинні бути числом")
                self._validate_stop_order(
                    side, stop_price, limit_price
                )

            if 'reduceOnly' in kwargs:
                kwargs['reduceOnly'] = str(kwargs['reduceOnly']).lower()
            
            logging.info(
                "Спроба розмістити ордер: %s, %s, %s, Кількість: %s, "
                "Параметри: %s",
                symbol, side, order_type, quantity, kwargs
            )
            
            # Захист від повторних помилок -1111
            for attempt in range(3):
                try:
                    order = self.client.futures_create_order(
                        symbol=symbol, side=side, type=order_type,
                        quantity=quantity, **kwargs
                    )
                    logging.info("Ордер успішно розміщено: %s", order)
                    return order
                except BinanceAPIException as e:
                    if e.code == -1111 and attempt < 2:
                        # Повторне форматування з більшою точністю
                        logging.warning(
                            "Спроба %d: Помилка precision для %s, переформатовуємо...",
                            attempt + 1, symbol
                        )
                        # Додаткове округлення для надмірно точних значень
                        if 'stopPrice' in kwargs:
                            kwargs['stopPrice'] = f"{float(kwargs['stopPrice']):.4f}"
                        if 'price' in kwargs:
                            kwargs['price'] = f"{float(kwargs['price']):.4f}"
                        continue
                    else:
                        raise

        except ValueError as e:
            logging.error("Помилка валідації ордера для %s: %s", symbol, e)
            return None
        except BinanceAPIException as e:
            logging.error("Помилка розміщення ордера для %s: %s", symbol, e)
            return None

    @_retry_on_api_error()
    def cancel_order(self, symbol: str, order_id: int) -> dict | None:
        """Скасовує активний ордер."""
        try:
            result = self.client.futures_cancel_order(
                symbol=symbol, orderId=order_id
            )
            logging.info(
                "Ордер %s для %s успішно скасовано.", order_id, symbol
            )
            return result
        except BinanceAPIException as e:
            logging.error(
                "Не вдалося скасувати ордер %s для %s: %s",
                order_id, symbol, e
            )
            return None

    @_retry_on_api_error()
    def cancel_and_replace_order(
        self, symbol: str, cancel_order_id: int, side: str, order_type: str,
        quantity: float, **kwargs
    ) -> dict | None:
        """Атомарно скасовує старий ордер і розміщує новий."""
        try:
            if 'reduceOnly' in kwargs:
                kwargs['reduceOnly'] = str(kwargs['reduceOnly']).lower()
            self.cancel_order(symbol, cancel_order_id)
            new_order = self.place_order(
                symbol, side, order_type, quantity, **kwargs
            )
            return new_order
        except (ValueError, BinanceAPIException) as e:
            logging.error(
                "Помилка при заміні ордера %s для %s: %s",
                cancel_order_id, symbol, e
            )
            return None

    @_retry_on_api_error()
    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Отримує список всіх відкритих ордерів."""
        try:
            params = {'symbol': symbol} if symbol else {}
            orders = self.client.futures_get_open_orders(**params)
            if isinstance(orders, list):
                return orders
            else:
                logging.error("API вернул не список, а %s", type(orders))
                return []
        except BinanceAPIException as e:
            logging.error("Не вдалося отримати відкриті ордери: %s", e)
            return []

    @_retry_on_api_error()
    def get_position_information(self, symbol: Optional[str] = None) -> list:
        """Отримує інформацію про позиції."""
        try:
            account_info = self.client.futures_account()
            positions = account_info.get('positions', [])
            if not isinstance(positions, list):
                logging.error("API вернул не список позиций, а %s", type(positions))
                return []
            if symbol:
                positions = [p for p in positions if p.get('symbol') == symbol]
            return positions
        except (BinanceAPIException, BinanceRequestException) as e:
            logging.error("Не вдалося отримати інформацію про позиції: %s", e)
            return []

    def get_open_positions(self) -> list:
        """Отримує список відкритих позицій (з ненульовими розмірами)."""
        try:
            all_positions = self.client.futures_position_information()
            if not isinstance(all_positions, list):
                logging.error("API вернул не список позиций, а %s", type(all_positions))
                return []
            return [
                p for p in all_positions 
                if float(p.get('positionAmt', 0)) != 0
            ]
        except BinanceAPIException as e:
            logging.error(
                "Не вдалося отримати відкриті позиції: %s", e
            )
            return []

    def place_market_order(self, symbol: str, side: str, quantity: float):
        """Розміщує ринковий ордер для закриття позиції."""
        try:
            result = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type=Client.ORDER_TYPE_MARKET,
                quantity=quantity,
                reduceOnly=True
            )
            logging.info(
                "Ринковий ордер розміщено: %s %s %s", 
                symbol, side, quantity
            )
            return result
        except BinanceAPIException as e:
            logging.error(
                "Помилка розміщення ринкового ордера %s: %s", 
                symbol, e
            )
            return None
