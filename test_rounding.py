#!/usr/bin/env python3
"""
Unit-тести для перевірки округлення цін та quantity згідно з фільтрами Binance.
"""

import unittest
from decimal import Decimal
from trading_bot.exchange_connector import BinanceFuturesConnector


class TestPriceQuantityRounding(unittest.TestCase):
    """Тестує правильність округлення цін та кількостей."""

    def setUp(self):
        """Налаштування тестових даних."""
        # Мокові фільтри для різних символів
        self.mock_filters = {
            'SUIUSDT': {
                'PRICE_FILTER': {'tickSize': '0.0001', 'minPrice': '0.0001', 'maxPrice': '1000'},
                'LOT_SIZE': {'stepSize': '0.1', 'minQty': '0.1', 'maxQty': '9000000'},
                'MIN_NOTIONAL': {'minNotional': '5.00000000'}
            },
            'BTCUSDT': {
                'PRICE_FILTER': {'tickSize': '0.1', 'minPrice': '0.1', 'maxPrice': '4529764'},
                'LOT_SIZE': {'stepSize': '0.001', 'minQty': '0.001', 'maxQty': '1000'},
                'MIN_NOTIONAL': {'minNotional': '5.00000000'}
            }
        }
        
        # Створюємо коннектор без реального API
        self.connector = BinanceFuturesConnector('test_key', 'test_secret', testnet=True)
        # Мокуємо метод get_exchange_filters
        self.connector.get_exchange_filters = self._mock_get_filters

    def _mock_get_filters(self, symbol: str) -> dict:
        """Мокова функція для отримання фільтрів."""
        return self.mock_filters.get(symbol, {})

    def test_round_price_suiusdt(self):
        """Тестує округлення ціни для SUIUSDT."""
        # Проблемна ціна з логу
        problematic_price = 3.5368066065884167
        tick_size = '0.0001'
        
        result = self.connector.round_price(problematic_price, tick_size)
        self.assertEqual(result, '3.5368')
        
        # Перевіряємо, що результат є валідним
        result_decimal = Decimal(result)
        tick_decimal = Decimal(tick_size)
        self.assertEqual(result_decimal % tick_decimal, Decimal('0'))

    def test_round_price_btcusdt(self):
        """Тестує округлення ціни для BTCUSDT."""
        price = 45123.456789
        tick_size = '0.1'
        
        result = self.connector.round_price(price, tick_size)
        self.assertEqual(result, '45123.4')

    def test_format_quantity_and_price_suiusdt(self):
        """Тестує повне форматування для SUIUSDT."""
        quantity = 6.9123456
        stop_price = 3.5368066065884167
        
        result = self.connector.format_quantity_and_price(
            'SUIUSDT', quantity, stop_price=stop_price
        )
        
        self.assertEqual(result['quantity'], 6.9)  # Округлено до stepSize 0.1
        self.assertEqual(result['stopPrice'], '3.5368')  # Округлено до tickSize 0.0001

    def test_min_notional_adjustment(self):
        """Тестує автоматичне збільшення quantity для дотримання minNotional."""
        # Тест з малою кількістю, яка не відповідає minNotional
        quantity = 0.1
        price = 10.0  # Загальна вартість: 1.0, менше minNotional 5.0
        
        result = self.connector.format_quantity_and_price(
            'SUIUSDT', quantity, price=price
        )
        
        # Quantity має бути збільшено
        total_value = float(result['quantity']) * float(result.get('price', price))
        self.assertGreaterEqual(total_value, 5.0)

    def test_precision_edge_cases(self):
        """Тестує крайні випадки з precision."""
        test_cases = [
            (0.00009999, '0.0001', '0.0000'),  # Менше мінімального tick
            (1.23456789, '0.0001', '1.2345'),  # Багато знаків після коми
            (1000.0, '0.1', '1000.0'),  # Точне значення
        ]
        
        for price, tick_size, expected in test_cases:
            with self.subTest(price=price, tick_size=tick_size):
                result = self.connector.round_price(price, tick_size)
                self.assertEqual(result, expected)

    def test_quantity_step_size(self):
        """Тестує округлення quantity згідно з stepSize."""
        from binance.helpers import round_step_size
        
        test_cases = [
            (6.9123456, '0.1', 6.9),
            (0.0015, '0.001', 0.001),
            (100.555, '1', 100),
        ]
        
        for qty, step, expected in test_cases:
            with self.subTest(qty=qty, step=step):
                result = round_step_size(qty, step)
                self.assertEqual(float(result), expected)


if __name__ == '__main__':
    unittest.main()
