"""
🔧 ORDER DEBUGGER
Детальна діагностика ордерів для торгової системи
"""

import logging
from typing import Dict, Optional, Any
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class OrderDebugger:
    """Клас для діагностики та логування ордерів"""
    
    def __init__(self, exchange=None):
        self.exchange = exchange
        self.order_history = []
        
    def debug_create_order(self, symbol: str, side: str, amount: float, price: float = None, order_type: str = "market") -> Dict[str, Any]:
        """
        Створення ордера з повним логуванням всіх етапів (синхронно)
        """
        try:
            logger.info(f"[ORDER_DEBUG] Початок створення ордера:")
            logger.info(f"  Symbol: {symbol}")
            logger.info(f"  Side: {side}")
            logger.info(f"  Amount: {amount}")
            logger.info(f"  Price: {price}")
            logger.info(f"  Type: {order_type}")
            
            # Перевірка підключення до біржі
            if not self.exchange:
                logger.error("[ORDER_DEBUG] Exchange не ініціалізований!")
                return {"error": "No exchange connection"}
            
            # Перевірка балансу (синхронно)
            try:
                balance = self.exchange.fetch_balance()
                logger.info(f"[ORDER_DEBUG] Баланс USDT: {balance.get('USDT', {}).get('free', 0)}")
            except Exception as e:
                logger.warning(f"[ORDER_DEBUG] Не вдалося отримати баланс: {e}")
            
            # Перевірка мінімальних вимог (синхронно з правильною логікою)
            try:
                markets = self.exchange.load_markets()
                market = markets.get(symbol)
                if market:
                    # Отримуємо всі мінімальні вимоги
                    min_notional = market.get('limits', {}).get('cost', {}).get('min', 5.0)
                    min_amount = market.get('limits', {}).get('amount', {}).get('min', 0.001)
                    
                    # Отримуємо точність
                    amount_precision = market.get('precision', {}).get('amount', 3)
                    
                    current_price = self.exchange.fetch_ticker(symbol)
                    market_price = current_price['last']
                    notional = amount * market_price
                    
                    logger.info(f"[ORDER_DEBUG] Мін. нотіонал: {min_notional}")
                    logger.info(f"[ORDER_DEBUG] Мін. кількість: {min_amount}")
                    logger.info(f"[ORDER_DEBUG] Точність: {amount_precision}")
                    logger.info(f"[ORDER_DEBUG] Поточний нотіонал: {notional}")
                    logger.info(f"[ORDER_DEBUG] Кількість: {amount}")
                    
                    # Перевірка мінімальної кількості
                    if amount < min_amount:
                        logger.error(f"[ORDER_DEBUG] Кількість занадто мала: {amount} < {min_amount}")
                        return {"error": "MIN_AMOUNT"}
                    
                    # Перевірка мінімального нотіоналу
                    if notional < min_notional:
                        logger.error(f"[ORDER_DEBUG] Нотіонал занадто малий: {notional} < {min_notional}")
                        return {"error": "MIN_NOTIONAL"}
                        
                    # Округлюємо кількість до правильної точності
                    if amount_precision:
                        if isinstance(amount_precision, float) and amount_precision < 1:
                            # Якщо точність як 1e-05, рахуємо decimal places
                            import math
                            decimal_places = abs(int(math.log10(amount_precision)))
                            amount = round(amount, decimal_places)
                        else:
                            # Якщо ціле число точності
                            amount = round(amount, int(amount_precision))
                    
                    logger.info(f"[ORDER_DEBUG] Округлена кількість: {amount}")
                        
            except Exception as e:
                logger.warning(f"[ORDER_DEBUG] Не вдалося перевірити ліміти: {e}")
            
            # Створення ордера (синхронно)
            order_result = None
            if order_type == "market":
                if side == "buy":
                    order_result = self.exchange.create_market_buy_order(symbol, amount)
                else:
                    order_result = self.exchange.create_market_sell_order(symbol, amount)
            elif order_type == "limit":
                order_result = self.exchange.create_limit_order(symbol, side, amount, price)
            
            # Логування результату
            if order_result:
                logger.info(f"[ORDER_SUCCESS] Ордер створено:")
                logger.info(f"  ID: {order_result.get('id')}")
                logger.info(f"  Status: {order_result.get('status')}")
                logger.info(f"  Filled: {order_result.get('filled', 0)}")
                logger.info(f"  Remaining: {order_result.get('remaining', 0)}")
                logger.info(f"  Fee: {order_result.get('fee')}")
                
                # Зберігаємо в історію
                self.order_history.append({
                    "timestamp": datetime.now(),
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    "order_type": order_type,
                    "result": order_result,
                    "success": True
                })
                
                return order_result
            else:
                logger.error("[ORDER_DEBUG] Ордер повернув None!")
                return {"error": "NULL_RESULT"}
                
        except Exception as e:
            logger.error(f"[ORDER_ERROR] Помилка створення ордера: {e}")
            logger.error(f"[ORDER_ERROR] Type: {type(e).__name__}")
            
            # Зберігаємо помилку в історію
            self.order_history.append({
                "timestamp": datetime.now(),
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "order_type": order_type,
                "error": str(e),
                "success": False
            })
            
            return {"error": str(e)}
    
    async def check_order_status(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Перевірка статусу ордера"""
        try:
            logger.info(f"[ORDER_CHECK] Перевірка ордера {order_id} для {symbol}")
            
            order = await self.exchange.fetch_order(order_id, symbol)
            
            logger.info(f"[ORDER_CHECK] Результат:")
            logger.info(f"  Status: {order.get('status')}")
            logger.info(f"  Filled: {order.get('filled', 0)}")
            logger.info(f"  Remaining: {order.get('remaining', 0)}")
            logger.info(f"  Average price: {order.get('average')}")
            
            return order
            
        except Exception as e:
            logger.error(f"[ORDER_CHECK] Помилка перевірки ордера: {e}")
            return {"error": str(e)}
    
    async def check_open_orders(self, symbol: str = None) -> list:
        """Перевірка відкритих ордерів"""
        try:
            logger.info(f"[ORDERS_CHECK] Перевірка відкритих ордерів для {symbol or 'всіх символів'}")
            
            orders = await self.exchange.fetch_open_orders(symbol)
            
            logger.info(f"[ORDERS_CHECK] Знайдено {len(orders)} відкритих ордерів:")
            for order in orders:
                logger.info(f"  {order['id']}: {order['symbol']} {order['side']} {order['amount']} @ {order['price']}")
            
            return orders
            
        except Exception as e:
            logger.error(f"[ORDERS_CHECK] Помилка перевірки ордерів: {e}")
            return []
    
    def get_order_history(self) -> list:
        """Отримати історію ордерів"""
        return self.order_history
    
    def print_diagnostics(self):
        """Вивести діагностичну інформацію"""
        logger.info(f"[DIAGNOSTICS] Всього спроб ордерів: {len(self.order_history)}")
        
        successful = [h for h in self.order_history if h.get('success')]
        failed = [h for h in self.order_history if not h.get('success')]
        
        logger.info(f"[DIAGNOSTICS] Успішних: {len(successful)}")
        logger.info(f"[DIAGNOSTICS] Невдалих: {len(failed)}")
        
        if failed:
            logger.info("[DIAGNOSTICS] Останні помилки:")
            for fail in failed[-3:]:  # Останні 3 помилки
                logger.info(f"  {fail['timestamp']}: {fail['symbol']} - {fail['error']}")

# Допоміжні функції для швидкої діагностики
async def quick_balance_check(exchange):
    """Швидка перевірка балансу"""
    try:
        balance = await exchange.fetch_balance()
        logger.info("[BALANCE_CHECK] Баланс:")
        for currency, data in balance.items():
            if isinstance(data, dict) and data.get('total', 0) > 0:
                logger.info(f"  {currency}: {data['total']} (вільно: {data['free']})")
        return balance
    except Exception as e:
        logger.error(f"[BALANCE_CHECK] Помилка: {e}")
        return None

async def quick_connection_check(exchange):
    """Швидка перевірка підключення"""
    try:
        server_time = await exchange.fetch_time()
        logger.info(f"[CONNECTION_CHECK] Підключення OK, серверний час: {datetime.fromtimestamp(server_time/1000)}")
        return True
    except Exception as e:
        logger.error(f"[CONNECTION_CHECK] Помилка підключення: {e}")
        return False

if __name__ == "__main__":
    # Тест модуля
    print("Order Debugger модуль завантажено успішно!")
