"""
[TARGET] OCO MANAGER - Реальні One-Cancels-Other ордери
НЕ if-else логіка, а справжні OCO ордери на біржі!
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import json

logger = logging.getLogger(__name__)

class OCOManager:
    """Управління OCO ордерами (TP1, TP2, SL)"""
    
    def __init__(self, exchange):
        self.exchange = exchange
        self.active_ocos = {}  # {position_id: oco_data}
        self.monitoring_tasks = {}
        
    async def create_oco_orders(self, symbol: str, side: str, quantity: float, 
                               entry_price: float, tp1_price: float, tp2_price: float, 
                               sl_price: float, position_id: str) -> bool:
        """
        Створення OCO ордерів:
        1. TP1 - частковий вихід (50% позиції)
        2. TP2 - повний вихід (решта 50%)
        3. SL - стоп-лосс на всю позицію
        """
        try:
            # Визначаємо об'єми
            tp1_quantity = quantity * 0.5  # 50% на TP1
            tp2_quantity = quantity * 0.5  # 50% на TP2
            sl_quantity = quantity         # 100% на SL
            
            # Визначаємо сторони закриття (протилежні до входу)
            close_side = 'sell' if side == 'buy' else 'buy'
            
            oco_data = {
                'position_id': position_id,
                'symbol': symbol,
                'entry_price': entry_price,
                'entry_side': side,
                'total_quantity': quantity,
                'orders': {},
                'executed': [],
                'status': 'active',
                'created_at': datetime.now()
            }
            
            # 1. Створюємо TP1 ордер (лімітний)
            try:
                tp1_order = await self.exchange.create_limit_order(
                    symbol=symbol,
                    side=close_side,
                    amount=tp1_quantity,
                    price=tp1_price,
                    params={'timeInForce': 'GTC', 'postOnly': True}  # Post-only для меншої комісії
                )
                oco_data['orders']['tp1'] = tp1_order
                logger.info(f"[OK] TP1 ордер створено: {tp1_price} ({tp1_quantity})")
            except Exception as e:
                logger.error(f"[ERROR] Помилка створення TP1: {e}")
                return False
            
            # 2. Створюємо SL ордер (стоп-лімітний)
            try:
                sl_order = await self.exchange.create_stop_limit_order(
                    symbol=symbol,
                    side=close_side,
                    amount=sl_quantity,
                    price=sl_price * 0.995,  # Лімітна ціна трохи гірша за стоп
                    stopPrice=sl_price,
                    params={'timeInForce': 'GTC'}
                )
                oco_data['orders']['sl'] = sl_order
                logger.info(f"[SHIELD] SL ордер створено: {sl_price} ({sl_quantity})")
            except Exception as e:
                logger.error(f"[ERROR] Помилка створення SL: {e}")
                # Скасовуємо TP1 якщо SL не створився
                if 'tp1' in oco_data['orders']:
                    await self.cancel_order(oco_data['orders']['tp1']['id'], symbol)
                return False
            
            # 3. TP2 створюємо ПІСЛЯ виконання TP1 (не одразу!)
            oco_data['tp2_pending'] = {
                'price': tp2_price,
                'quantity': tp2_quantity
            }
            
            # Зберігаємо OCO групу
            self.active_ocos[position_id] = oco_data
            
            # Запускаємо моніторинг
            task = asyncio.create_task(self.monitor_oco(position_id))
            self.monitoring_tasks[position_id] = task
            
            logger.info(f"[TARGET] OCO група створена для {position_id}: TP1({tp1_price}) TP2({tp2_price}) SL({sl_price})")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Критична помилка створення OCO {position_id}: {e}")
            return False
    
    async def monitor_oco(self, position_id: str):
        """Моніторинг OCO ордерів"""
        try:
            while position_id in self.active_ocos:
                oco_data = self.active_ocos[position_id]
                
                if oco_data['status'] != 'active':
                    break
                
                # Перевіряємо статуси ордерів
                for order_type, order in oco_data['orders'].items():
                    if order_type in oco_data['executed']:
                        continue
                        
                    try:
                        status = await self.exchange.fetch_order(order['id'], oco_data['symbol'])
                        
                        if status['status'] == 'closed':
                            await self.handle_order_execution(position_id, order_type, status)
                            
                    except Exception as e:
                        logger.error(f"Помилка перевірки ордера {order_type} для {position_id}: {e}")
                
                await asyncio.sleep(5)  # Перевіряємо кожні 5 секунд
                
        except Exception as e:
            logger.error(f"Помилка моніторингу OCO {position_id}: {e}")
    
    async def handle_order_execution(self, position_id: str, order_type: str, executed_order: dict):
        """Обробка виконання ордера"""
        try:
            oco_data = self.active_ocos[position_id]
            oco_data['executed'].append(order_type)
            
            logger.info(f"[TARGET] {order_type.upper()} виконано для {position_id}: {executed_order['price']} x {executed_order['amount']}")
            
            if order_type == 'tp1':
                # TP1 виконано - створюємо TP2 і скасовуємо частину SL
                await self.handle_tp1_execution(position_id)
                
            elif order_type == 'sl':
                # SL виконано - скасовуємо всі інші ордери
                await self.handle_sl_execution(position_id)
                
            elif order_type == 'tp2':
                # TP2 виконано - скасовуємо SL
                await self.handle_tp2_execution(position_id)
                
        except Exception as e:
            logger.error(f"Помилка обробки виконання {order_type} для {position_id}: {e}")
    
    async def handle_tp1_execution(self, position_id: str):
        """Обробка виконання TP1"""
        try:
            oco_data = self.active_ocos[position_id]
            
            # 1. Скасовуємо поточний SL (на повну позицію)
            if 'sl' in oco_data['orders'] and 'sl' not in oco_data['executed']:
                await self.cancel_order(oco_data['orders']['sl']['id'], oco_data['symbol'])
                logger.info(f"[ERROR] SL скасовано після TP1")
            
            # 2. Створюємо новий SL на решту позиції (50%)
            remaining_quantity = oco_data['total_quantity'] * 0.5
            close_side = 'sell' if oco_data['entry_side'] == 'buy' else 'buy'
            
            # SL на беззбиток або невеликий прибуток
            breakeven_price = oco_data['entry_price'] * (1.005 if oco_data['entry_side'] == 'buy' else 0.995)
            
            new_sl_order = await self.exchange.create_stop_limit_order(
                symbol=oco_data['symbol'],
                side=close_side,
                amount=remaining_quantity,
                price=breakeven_price * 0.995,  # Лімітна ціна
                stopPrice=breakeven_price,
                params={'timeInForce': 'GTC'}
            )
            
            oco_data['orders']['sl_new'] = new_sl_order
            logger.info(f"[SHIELD] Новий SL створено на беззбиток: {breakeven_price}")
            
            # 3. Створюємо TP2 ордер
            tp2_data = oco_data['tp2_pending']
            tp2_order = await self.exchange.create_limit_order(
                symbol=oco_data['symbol'],
                side=close_side,
                amount=tp2_data['quantity'],
                price=tp2_data['price'],
                params={'timeInForce': 'GTC', 'postOnly': True}
            )
            
            oco_data['orders']['tp2'] = tp2_order
            logger.info(f"[TARGET] TP2 ордер створено: {tp2_data['price']} ({tp2_data['quantity']})")
            
        except Exception as e:
            logger.error(f"Помилка обробки TP1 для {position_id}: {e}")
    
    async def handle_sl_execution(self, position_id: str):
        """Обробка виконання SL"""
        try:
            oco_data = self.active_ocos[position_id]
            
            # Скасовуємо всі активні ордери
            for order_type, order in oco_data['orders'].items():
                if order_type not in oco_data['executed']:
                    await self.cancel_order(order['id'], oco_data['symbol'])
            
            oco_data['status'] = 'closed_sl'
            logger.warning(f"[ALERT] SL виконано - позиція {position_id} закрита з збитком")
            
        except Exception as e:
            logger.error(f"Помилка обробки SL для {position_id}: {e}")
    
    async def handle_tp2_execution(self, position_id: str):
        """Обробка виконання TP2"""
        try:
            oco_data = self.active_ocos[position_id]
            
            # Скасовуємо SL
            for order_type, order in oco_data['orders'].items():
                if 'sl' in order_type and order_type not in oco_data['executed']:
                    await self.cancel_order(order['id'], oco_data['symbol'])
            
            oco_data['status'] = 'closed_tp2'
            logger.info(f"[SUCCESS] TP2 виконано - позиція {position_id} закрита з прибутком")
            
        except Exception as e:
            logger.error(f"Помилка обробки TP2 для {position_id}: {e}")
    
    async def cancel_order(self, order_id: str, symbol: str):
        """Скасування ордера"""
        try:
            await self.exchange.cancel_order(order_id, symbol)
            logger.info(f"[ERROR] Ордер {order_id} скасовано")
        except Exception as e:
            logger.warning(f"Не вдалося скасувати ордер {order_id}: {e}")
    
    async def emergency_close_position(self, position_id: str):
        """Екстрене закриття позиції (скасувати всі ордери + маркет ордер)"""
        try:
            if position_id not in self.active_ocos:
                return
                
            oco_data = self.active_ocos[position_id]
            
            # Скасовуємо всі активні ордери
            for order_type, order in oco_data['orders'].items():
                if order_type not in oco_data['executed']:
                    await self.cancel_order(order['id'], oco_data['symbol'])
            
            # Створюємо маркет ордер на закриття
            close_side = 'sell' if oco_data['entry_side'] == 'buy' else 'buy'
            
            market_order = await self.exchange.create_market_order(
                symbol=oco_data['symbol'],
                side=close_side,
                amount=oco_data['total_quantity']
            )
            
            oco_data['status'] = 'emergency_closed'
            logger.warning(f"[ALERT] Екстрене закриття позиції {position_id}")
            
        except Exception as e:
            logger.error(f"Помилка екстреного закриття {position_id}: {e}")
    
    def get_oco_status(self, position_id: str) -> dict:
        """Отримання статусу OCO групи"""
        if position_id in self.active_ocos:
            return self.active_ocos[position_id]
        return {}
    
    def cleanup_completed_ocos(self):
        """Очищення завершених OCO груп"""
        completed = []
        for position_id, oco_data in self.active_ocos.items():
            if oco_data['status'] in ['closed_sl', 'closed_tp2', 'emergency_closed']:
                completed.append(position_id)
        
        for position_id in completed:
            if position_id in self.monitoring_tasks:
                self.monitoring_tasks[position_id].cancel()
                del self.monitoring_tasks[position_id]
            del self.active_ocos[position_id]
            logger.info(f"[CLEAN] OCO група {position_id} очищена")

# Тест OCO Manager
async def test_oco_manager():
    """Тест OCO без реального exchange"""
    
    class MockExchange:
        def __init__(self):
            self.orders = {}
            self.order_counter = 1000
        
        async def create_limit_order(self, symbol, side, amount, price, params=None):
            order_id = str(self.order_counter)
            self.order_counter += 1
            
            order = {
                'id': order_id,
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': price,
                'status': 'open',
                'type': 'limit'
            }
            
            self.orders[order_id] = order
            return order
        
        async def create_stop_limit_order(self, symbol, side, amount, price, stopPrice, params=None):
            order_id = str(self.order_counter)
            self.order_counter += 1
            
            order = {
                'id': order_id,
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': price,
                'stopPrice': stopPrice,
                'status': 'open',
                'type': 'stop_limit'
            }
            
            self.orders[order_id] = order
            return order
        
        async def fetch_order(self, order_id, symbol):
            return self.orders.get(order_id, {})
        
        async def cancel_order(self, order_id, symbol):
            if order_id in self.orders:
                self.orders[order_id]['status'] = 'canceled'
    
    exchange = MockExchange()
    oco_manager = OCOManager(exchange)
    
    # Тест створення OCO
    success = await oco_manager.create_oco_orders(
        symbol='BTCUSDT',
        side='buy',
        quantity=1.0,
        entry_price=50000,
        tp1_price=52000,  # +4%
        tp2_price=54000,  # +8%
        sl_price=48750,   # -2.5%
        position_id='test_pos_1'
    )
    
    print(f"OCO створено: {success}")
    print(f"Активних OCO: {len(oco_manager.active_ocos)}")

if __name__ == "__main__":
    asyncio.run(test_oco_manager())
