#!/usr/bin/env python3
"""
Тестування мережевої стійкості торгового бота.
"""

import logging
import sys
from unittest.mock import Mock, patch
import requests.exceptions
from trading_bot.engine import Engine
from trading_bot.exchange_connector import BinanceFuturesConnector
from trading_bot.plan_parser import PlanParser


def test_network_error_handling():
    """Тестує обробку мережевих помилок."""
    
    # Налаштовуємо логування
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        # Завантажуємо план
        parser = PlanParser('data/trading_plan.json')
        if not parser.load_and_validate():
            logger.error("Не вдалося завантажити торговий план")
            return False
            
        plan = parser.plan
        logger.info(f"✓ План завантажено: {plan.plan_date}")
        
        # Створюємо мок-обʼєкти
        mock_exchange = Mock(spec=BinanceFuturesConnector)
        mock_notifier = Mock()
        mock_journal = Mock()
        mock_risk_manager = Mock()
        
        # Налаштовуємо мок exchange для симуляції мережевих помилок
        mock_exchange.get_open_orders.side_effect = requests.exceptions.ReadTimeout("Connection timeout")
        mock_exchange.get_position_information.side_effect = requests.exceptions.ConnectTimeout("Connection error")
        
        # Створюємо engine
        engine = Engine(
            plan_parser=parser,
            exchange_connector=mock_exchange,
            notifier=mock_notifier,
            journal=mock_journal
        )
        engine.risk_manager = mock_risk_manager
        
        logger.info("✓ Engine створено успішно")
        
        # Тестуємо _monitor_oco_orders з мережевими помилками
        logger.info("Тестуємо _monitor_oco_orders з мережевими помилками...")
        
        # Додаємо тестові OCO ордери
        engine.oco_orders = {
            'BTCUSDT': {
                'is_active': True,
                'buy_order_id': 123,
                'sell_order_id': 456,
                'side': 'BUY',
                'size': 0.1,
                'entry_price': 50000
            }
        }
        
        # Викликаємо метод - він повинен gracefully обробляти помилки
        engine._monitor_oco_orders()
        logger.info("✓ _monitor_oco_orders обробив мережеві помилки gracefully")
        
        # Тестуємо _manage_open_positions з мережевими помилками
        logger.info("Тестуємо _manage_open_positions з мережевими помилками...")
        engine._manage_open_positions()
        logger.info("✓ _manage_open_positions обробив мережеві помилки gracefully")
        
        logger.info("🎉 Всі тести мережевої стійкості пройшли успішно!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Помилка під час тестування: {e}")
        return False


if __name__ == "__main__":
    success = test_network_error_handling()
    sys.exit(0 if success else 1)
