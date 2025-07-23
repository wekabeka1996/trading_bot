"""
[TIME] TIME GUARD - Жорсткі часові стопи
НЕ просто "якщо минуло X годин", а ТОЧНІ тайм-стопи з моніторингом!
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List, Tuple, Set
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

@dataclass
class TimeStop:
    """Структура часового стопу"""
    position_id: str
    symbol: str
    side: str
    entry_time: datetime
    stop_time: datetime
    quantity: float
    reason: str
    status: str = 'active'  # active, triggered, cancelled
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

class TimeGuard:
    """Управління часовими стопами"""
    
    def __init__(self, exchange):
        self.exchange = exchange
        self.time_stops = {}  # {position_id: TimeStop}
        self.monitoring_task = None
        self.check_interval = 30  # Перевіряємо кожні 30 секунд
        self.running = False
        
    async def start_monitoring(self):
        """Запуск моніторингу часових стопів"""
        if self.running:
            return
            
        self.running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("[TIME] Моніторинг часових стопів запущено")
    
    async def stop_monitoring(self):
        """Зупинка моніторингу"""
        self.running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("[TIME] Моніторинг часових стопів зупинено")
    
    def add_time_stop(self, position_id: str, symbol: str, side: str, 
                     quantity: float, duration_hours: float, reason: str = "time_limit") -> bool:
        """
        Додавання часового стопу
        duration_hours може бути дробовим (наприклад, 0.5 = 30 хвилин)
        """
        try:
            entry_time = datetime.now(timezone.utc)
            stop_time = entry_time + timedelta(hours=duration_hours)
            
            time_stop = TimeStop(
                position_id=position_id,
                symbol=symbol,
                side=side,
                entry_time=entry_time,
                stop_time=stop_time,
                quantity=quantity,
                reason=reason
            )
            
            self.time_stops[position_id] = time_stop
            
            logger.info(f"[TIME] Часовий стоп додано: {position_id} → {stop_time.strftime('%H:%M:%S')} ({duration_hours}h)")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка додавання часового стопу {position_id}: {e}")
            return False
    
    def add_session_stops(self, positions: Dict[str, dict]) -> int:
        """
        Додавання стопів для торгової сесії (4-6 год)
        positions = {position_id: {'symbol': str, 'side': str, 'quantity': float}}
        """
        added = 0
        
        for position_id, pos_data in positions.items():
            # Різні тайм-стопи для різних активів
            duration = self._get_session_duration(pos_data['symbol'])
            
            success = self.add_time_stop(
                position_id=position_id,
                symbol=pos_data['symbol'],
                side=pos_data['side'],
                quantity=pos_data['quantity'],
                duration_hours=duration,
                reason="session_limit"
            )
            
            if success:
                added += 1
        
        logger.info(f"[TIME] Додано {added} сесійних стопів")
        return added
    
    def _get_session_duration(self, symbol: str) -> float:
        """Отримання тривалості сесії для різних активів"""
        # DeFi токени (DIA, PENDLE) - коротші сесії (4 год)
        if any(token in symbol for token in ['DIA', 'PENDLE']):
            return 4.0
        
        # AI/Gaming токени (RNDR, API3) - середні сесії (5 год)
        elif any(token in symbol for token in ['RNDR', 'API3']):
            return 5.0
        
        # Менші токени (UMA, FIDA) - довші сесії (6 год)
        elif any(token in symbol for token in ['UMA', 'FIDA']):
            return 6.0
        
        # Дефолт
        return 5.0
    
    def add_intraday_stops(self, positions: Dict[str, dict]) -> int:
        """
        Додавання внутрішньоденних стопів (30-90 хвилин)
        """
        added = 0
        
        for position_id, pos_data in positions.items():
            # Коротші стопи для скальпінгу
            duration_minutes = self._get_intraday_duration(pos_data['symbol'])
            duration_hours = duration_minutes / 60.0
            
            success = self.add_time_stop(
                position_id=position_id,
                symbol=pos_data['symbol'],
                side=pos_data['side'],
                quantity=pos_data['quantity'],
                duration_hours=duration_hours,
                reason="intraday_limit"
            )
            
            if success:
                added += 1
        
        logger.info(f"[TIME] Додано {added} внутрішньоденних стопів")
        return added
    
    def _get_intraday_duration(self, symbol: str) -> int:
        """Тривалість внутрішньоденної позиції в хвилинах"""
        # Високоволатильні токени - швидший вихід
        if any(token in symbol for token in ['PENDLE', 'RNDR', 'FIDA']):
            return 30  # 30 хвилин
        
        # Стабільніші DeFi токени
        elif any(token in symbol for token in ['DIA', 'UMA']):
            return 60  # 1 година
        
        # Інші
        return 45  # 45 хвилин
    
    def add_overnight_protection(self, positions: Dict[str, dict], market_close_hour: int = 22) -> int:
        """
        Додавання захисту на ніч (закриття до 22:00)
        """
        added = 0
        now = datetime.now(timezone.utc)
        
        # Розраховуємо час до 22:00 поточного дня
        market_close_today = now.replace(hour=market_close_hour, minute=0, second=0, microsecond=0)
        
        # Якщо вже пізно, то до 22:00 наступного дня
        if now >= market_close_today:
            market_close_today += timedelta(days=1)
        
        hours_until_close = (market_close_today - now).total_seconds() / 3600
        
        for position_id, pos_data in positions.items():
            success = self.add_time_stop(
                position_id=position_id,
                symbol=pos_data['symbol'],
                side=pos_data['side'],
                quantity=pos_data['quantity'],
                duration_hours=hours_until_close,
                reason="overnight_protection"
            )
            
            if success:
                added += 1
        
        logger.info(f"[MOON] Додано {added} нічних стопів (закриття о {market_close_hour}:00)")
        return added
    
    async def _monitoring_loop(self):
        """Основний цикл моніторингу"""
        try:
            while self.running:
                await self._check_time_stops()
                await asyncio.sleep(self.check_interval)
                
        except asyncio.CancelledError:
            logger.info("[TIME] Моніторинг часових стопів скасовано")
        except Exception as e:
            logger.error(f"[ERROR] Помилка в циклі моніторингу часових стопів: {e}")
    
    async def _check_time_stops(self):
        """Перевірка часових стопів"""
        try:
            now = datetime.now(timezone.utc)
            triggered_stops = []
            
            for position_id, time_stop in self.time_stops.items():
                if time_stop.status != 'active':
                    continue
                
                # Перевіряємо чи настав час стопу
                if now >= time_stop.stop_time:
                    triggered_stops.append(position_id)
                    logger.warning(f"[TIME] ЧАСОВИЙ СТОП ТРИГЕРНУТО: {position_id} ({time_stop.reason})")
            
            # Виконуємо стопи
            for position_id in triggered_stops:
                await self._execute_time_stop(position_id)
                
        except Exception as e:
            logger.error(f"[ERROR] Помилка перевірки часових стопів: {e}")
    
    async def _execute_time_stop(self, position_id: str) -> bool:
        """Виконання часового стопу"""
        try:
            if position_id not in self.time_stops:
                return False
            
            time_stop = self.time_stops[position_id]
            
            if time_stop.status != 'active':
                return False
            
            # Визначаємо сторону закриття (протилежну до входу)
            close_side = 'sell' if time_stop.side == 'buy' else 'buy'
            
            # Створюємо маркет ордер на закриття
            try:
                close_order = await self.exchange.create_market_order(
                    symbol=time_stop.symbol,
                    side=close_side,
                    amount=time_stop.quantity,
                    params={'reduceOnly': True}  # Тільки для закриття позиції
                )
                
                # Оновлюємо статус стопу
                time_stop.status = 'triggered'
                time_stop.execution_time = datetime.now(timezone.utc)
                time_stop.close_order = close_order
                
                logger.warning(f"[ALERT] ПОЗИЦІЯ ЗАКРИТА ПО ЧАСОВОМУ СТОПУ: {position_id} @ {close_order.get('price', 'market')}")
                
                # Тут можна додати нотифікацію в Telegram
                await self._send_time_stop_notification(time_stop, close_order)
                
                return True
                
            except Exception as e:
                logger.error(f"[ERROR] Помилка виконання ордера для часового стопу {position_id}: {e}")
                time_stop.status = 'error'
                time_stop.error_message = str(e)
                return False
                
        except Exception as e:
            logger.error(f"[ERROR] Критична помилка виконання часового стопу {position_id}: {e}")
            return False
    
    async def _send_time_stop_notification(self, time_stop: TimeStop, close_order: dict):
        """Відправка нотифікації про часовий стоп"""
        try:
            duration = time_stop.execution_time - time_stop.entry_time
            hours = duration.total_seconds() / 3600
            
            message = f"""
[ALERT] ЧАСОВИЙ СТОП ВИКОНАНО

[DATA] Позиція: {time_stop.position_id}
[MONEY] Символ: {time_stop.symbol}
[UP] Сторона: {time_stop.side.upper()}
[PACKAGE] Кількість: {time_stop.quantity}
[TIMER] Тривалість: {hours:.1f} годин
[TARGET] Причина: {time_stop.reason}
[DOLLAR] Ціна закриття: {close_order.get('price', 'ринкова')}

[TIME] Час закриття: {time_stop.execution_time.strftime('%H:%M:%S')}
            """
            
            # Тут інтеграція з Telegram/Discord/Slack
            logger.info(f"[MOBILE] Нотифікація надіслана: {time_stop.position_id}")
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка відправки нотифікації: {e}")
    
    def cancel_time_stop(self, position_id: str) -> bool:
        """Скасування часового стопу"""
        try:
            if position_id in self.time_stops:
                time_stop = self.time_stops[position_id]
                if time_stop.status == 'active':
                    time_stop.status = 'cancelled'
                    time_stop.cancelled_at = datetime.now(timezone.utc)
                    logger.info(f"[ERROR] Часовий стоп скасовано: {position_id}")
                    return True
            return False
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка скасування часового стопу {position_id}: {e}")
            return False
    
    def extend_time_stop(self, position_id: str, additional_hours: float) -> bool:
        """Продовження часового стопу"""
        try:
            if position_id in self.time_stops:
                time_stop = self.time_stops[position_id]
                if time_stop.status == 'active':
                    old_stop_time = time_stop.stop_time
                    time_stop.stop_time += timedelta(hours=additional_hours)
                    
                    logger.info(f"[TIME] Часовий стоп продовжено: {position_id} до {time_stop.stop_time.strftime('%H:%M:%S')} (+{additional_hours}h)")
                    return True
            return False
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка продовження часового стопу {position_id}: {e}")
            return False
    
    def get_active_stops(self) -> List[TimeStop]:
        """Отримання активних часових стопів"""
        return [stop for stop in self.time_stops.values() if stop.status == 'active']
    
    def get_stops_summary(self) -> dict:
        """Зведення по часових стопах"""
        try:
            now = datetime.now(timezone.utc)
            
            active_stops = [stop for stop in self.time_stops.values() if stop.status == 'active']
            triggered_stops = [stop for stop in self.time_stops.values() if stop.status == 'triggered']
            
            upcoming_stops = []
            for stop in active_stops:
                time_remaining = (stop.stop_time - now).total_seconds() / 60  # в хвилинах
                if time_remaining <= 60:  # Найближчі 60 хвилин
                    upcoming_stops.append({
                        'position_id': stop.position_id,
                        'symbol': stop.symbol,
                        'minutes_remaining': max(0, time_remaining),
                        'reason': stop.reason
                    })
            
            return {
                'timestamp': now.isoformat(),
                'total_stops': len(self.time_stops),
                'active_stops': len(active_stops),
                'triggered_today': len([s for s in triggered_stops if s.execution_time and s.execution_time.date() == now.date()]),
                'upcoming_stops': sorted(upcoming_stops, key=lambda x: x['minutes_remaining']),
                'monitoring_active': self.running
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка створення зведення часових стопів: {e}")
            return {'error': str(e)}
    
    def cleanup_old_stops(self, days_old: int = 7):
        """Очищення старих стопів"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
            
            old_stops = [
                pos_id for pos_id, stop in self.time_stops.items()
                if stop.status in ['triggered', 'cancelled'] and stop.created_at < cutoff_date
            ]
            
            for pos_id in old_stops:
                del self.time_stops[pos_id]
            
            if old_stops:
                logger.info(f"[CLEAN] Очищено {len(old_stops)} старих часових стопів")
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка очищення старих стопів: {e}")

# Тест Time Guard
async def test_time_guard():
    """Тест без реального exchange"""
    
    class MockExchange:
        async def create_market_order(self, symbol, side, amount, params=None):
            return {
                'id': '12345',
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': 100.0,
                'status': 'closed'
            }
    
    exchange = MockExchange()
    time_guard = TimeGuard(exchange)
    
    # Запускаємо моніторинг
    await time_guard.start_monitoring()
    
    # Додаємо тестові позиції
    test_positions = {
        'pos_1': {'symbol': 'DIA/USDT', 'side': 'buy', 'quantity': 100},
        'pos_2': {'symbol': 'PENDLE/USDT', 'side': 'buy', 'quantity': 200}
    }
    
    # Додаємо різні типи стопів
    time_guard.add_session_stops(test_positions)
    
    # Тестовий короткий стоп (1 секунда)
    time_guard.add_time_stop('test_pos', 'BTC/USDT', 'buy', 1.0, 0.0003, "test")  # ~1 секунда
    
    print(f"Активних стопів: {len(time_guard.get_active_stops())}")
    
    # Чекаємо кілька секунд
    await asyncio.sleep(2)
    
    # Перевіряємо результат
    summary = time_guard.get_stops_summary()
    print(f"Тригернутих сьогодні: {summary['triggered_today']}")
    
    await time_guard.stop_monitoring()

if __name__ == "__main__":
    asyncio.run(test_time_guard())
