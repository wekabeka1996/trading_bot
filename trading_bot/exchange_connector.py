# trading_bot/exchange_connector.py
# Цей модуль інкапсулює всю логіку взаємодії з API Binance Futures.
"""Інкапсулює логіку для взаємодії з API Binance Futures."""

import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from tenacity import (
    retry, stop_after_attempt, wait_exponential, retry_if_exception_type
)


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
                ConnectionError, TimeoutError
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

    @_retry_on_api_error()
    def check_connection(self) -> bool:
        """Перевіряє з'єднання з API та валідність ключів."""
        try:
            self.client.futures_account_balance()
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
            # pylint: disable=no-member
            data = self.client.futures_premium_index(symbol=symbol)
            return {
                'markPrice': float(data['markPrice']),
                'lastFundingRate': float(data['lastFundingRate'])
            }
        except BinanceAPIException as e:
            logging.error(
                "Не вдалося отримати funding rate для %s: %s", symbol, e
            )
            return None

    @_retry_on_api_error()
    def get_historical_klines(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list:
        """Отримує історичні дані свічок (klines) для символу."""
        try:
            return self.client.futures_klines(
                symbol=symbol, interval=interval, limit=limit
            )
        except BinanceAPIException as e:
            logging.error(
                "Не вдалося отримати klines для %s: %s", symbol, e
            )
            return []

    @_retry_on_api_error()
    def get_futures_account_balance(self, asset: str = 'USDT') -> float | None:
        try:
            balance_info = self.client.futures_account_balance()
            for item in balance_info:
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
            return float(ticker['lastPrice'])
        except BinanceAPIException as e:
            logging.error("Не вдалося отримати ціну для %s: %s", symbol, e)
            return None

    def _validate_stop_order(
        self, side: str, stop_price: float, limit_price: float = None
    ):
        """Валідація параметрів STOP ордера перед відправкою на біржу."""
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

    @_retry_on_api_error()
    def place_order(
        self, symbol: str, side: str, order_type: str, quantity: float, **kwargs
    ) -> dict | None:
        """Універсальний метод для розміщення ордера."""
        try:
            # Валідація STOP ордерів перед відправкою
            if order_type in ["STOP", "STOP_MARKET"] and "stopPrice" in kwargs:
                self._validate_stop_order(
                    side, kwargs["stopPrice"], kwargs.get("price")
                )

            if 'reduceOnly' in kwargs:
                kwargs['reduceOnly'] = str(kwargs['reduceOnly']).lower()
            logging.info(
                "Спроба розмістити ордер: %s, %s, %s, Кількість: %s, "
                "Параметри: %s",
                symbol, side, order_type, quantity, kwargs
            )
            order = self.client.futures_create_order(
                symbol=symbol, side=side, type=order_type,
                quantity=quantity, **kwargs
            )
            logging.info("Ордер успішно розміщено: %s", order)
            return order
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
    def get_open_orders(self, symbol: str = None) -> list:
        """Отримує список всіх відкритих ордерів."""
        try:
            params = {'symbol': symbol} if symbol else {}
            return self.client.futures_get_open_orders(**params)
        except BinanceAPIException as e:
            logging.error("Не вдалося отримати відкриті ордери: %s", e)
            return []

    @_retry_on_api_error()
    def get_position_information(self, symbol: str = None) -> list:
        """Отримує інформацію про відкриті позиції."""
        try:
            positions = self.client.futures_position_information()
            if symbol:
                return [p for p in positions if p['symbol'] == symbol]
            return positions
        except BinanceAPIException as e:
            logging.error(
                "Не вдалося отримати інформацію про позиції: %s", e
            )
            return []
