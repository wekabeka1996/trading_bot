"""
[SHIELD] HEDGE MANAGER - Справжнє хеджування через BTC dominance
НЕ простий short BTC, а ДИНАМІЧНЕ хеджування beta=0.4!
"""

import asyncio
import logging
from datetime import datetime, timedelta
import numpy as np
from typing import Dict, Optional, List, Tuple
import json

logger = logging.getLogger(__name__)

class HedgeManager:
    """Динамічне хеджування через BTC dominance"""
    
    def __init__(self, exchange, target_beta=0.4):
        self.exchange = exchange
        self.target_beta = target_beta  # Цільовий бета-коефіцієнт
        self.btc_dominance_threshold = 55.0  # Поріг активації хеджу
        self.hedge_positions = {}  # {symbol: hedge_data}
        self.market_data = {}
        self.last_dominance_check = None
        self.hedge_active = False
        
    async def initialize_hedge_system(self):
        """Ініціалізація системи хеджування"""
        try:
            logger.info("[SHIELD] Ініціалізація системи хеджування...")
            
            # Завантажуємо поточні ринкові дані
            await self.update_market_data()
            
            # Перевіряємо BTC dominance
            await self.check_btc_dominance()
            
            logger.info("[OK] Система хеджування ініціалізована")
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка ініціалізації хеджування: {e}")
    
    async def update_market_data(self):
        """Оновлення ринкових даних"""
        try:
            # Отримуємо тікери основних пар
            symbols = ['BTC/USDT', 'ETH/USDT']
            
            for symbol in symbols:
                ticker = await self.exchange.fetch_ticker(symbol)
                self.market_data[symbol] = {
                    'price': ticker['last'],
                    'volume_24h': ticker['quoteVolume'],
                    'change_24h': ticker['percentage'],
                    'timestamp': datetime.now()
                }
            
            logger.info("[DATA] Ринкові дані оновлено")
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка оновлення ринкових даних: {e}")
    
    async def get_btc_dominance(self) -> Optional[float]:
        """
        Отримання BTC dominance
        В реальній системі це API до CoinGecko/CoinMarketCap
        """
        try:
            # В тестовому режимі симулюємо dominance на основі BTC/ETH ratio
            if 'BTC/USDT' in self.market_data and 'ETH/USDT' in self.market_data:
                btc_price = self.market_data['BTC/USDT']['price']
                eth_price = self.market_data['ETH/USDT']['price']
                
                # Спрощена симуляція: якщо BTC/ETH ratio високий, то dominance теж
                btc_eth_ratio = btc_price / eth_price if eth_price > 0 else 20
                
                # Нормалізуємо до діапазону 45-65%
                simulated_dominance = min(65, max(45, 50 + (btc_eth_ratio - 20) * 2))
                
                logger.info(f"[UP] BTC Dominance (симуляція): {simulated_dominance:.1f}%")
                return simulated_dominance
            
            return None
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка отримання BTC dominance: {e}")
            return None
    
    async def check_btc_dominance(self) -> bool:
        """Перевірка BTC dominance і активація хеджу"""
        try:
            dominance = await self.get_btc_dominance()
            
            if dominance is None:
                return False
            
            self.last_dominance_check = datetime.now()
            
            # Логіка активації/деактивації хеджу
            if dominance >= self.btc_dominance_threshold and not self.hedge_active:
                logger.warning(f"[ALERT] BTC Dominance {dominance:.1f}% >= {self.btc_dominance_threshold}% - Активуємо хедж!")
                self.hedge_active = True
                return True
                
            elif dominance < (self.btc_dominance_threshold - 2) and self.hedge_active:
                logger.info(f"[OK] BTC Dominance {dominance:.1f}% знизилася - Деактивуємо хедж")
                self.hedge_active = False
                await self.close_all_hedges()
                return False
            
            return self.hedge_active
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка перевірки BTC dominance: {e}")
            return False
    
    async def calculate_hedge_sizes(self, long_positions: Dict[str, float]) -> Dict[str, float]:
        """
        Розрахунок розмірів хеджів для досягнення цільового бета
        long_positions = {symbol: position_size_usd}
        """
        try:
            if not long_positions:
                return {}
            
            total_long_exposure = sum(long_positions.values())
            
            # Розраховуємо бета-коефіцієнти позицій відносно BTC
            position_betas = await self.calculate_position_betas(list(long_positions.keys()))
            
            # Зважений бета портфеля
            portfolio_beta = 0
            for symbol, size in long_positions.items():
                weight = size / total_long_exposure
                beta = position_betas.get(symbol, 1.0)  # Дефолт бета = 1.0
                portfolio_beta += weight * beta
            
            logger.info(f"[DATA] Поточний портфельний бета: {portfolio_beta:.3f}")
            
            # Розрахунок необхідного хеджування
            # Target_Beta = Current_Beta + Hedge_Weight * Hedge_Beta
            # Hedge_Weight = (Target_Beta - Current_Beta) / Hedge_Beta
            
            hedge_sizes = {}
            
            if portfolio_beta > self.target_beta:
                # Потрібен short хедж BTC/ETH
                excess_beta = portfolio_beta - self.target_beta
                
                # BTC хедж (beta ≈ 1.0 for short)
                btc_hedge_weight = excess_beta * 0.7  # 70% хеджу через BTC
                btc_hedge_size = total_long_exposure * btc_hedge_weight
                
                # ETH хедж (beta ≈ 1.2-1.5 for short)
                eth_hedge_weight = excess_beta * 0.3 / 1.3  # 30% через ETH з поправкою на бета
                eth_hedge_size = total_long_exposure * eth_hedge_weight
                
                hedge_sizes = {
                    'BTC/USDT': btc_hedge_size,
                    'ETH/USDT': eth_hedge_size
                }
                
                logger.info(f"[SHIELD] Розраховано хедж: BTC ${btc_hedge_size:,.0f}, ETH ${eth_hedge_size:,.0f}")
            
            return hedge_sizes
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка розрахунку розмірів хеджу: {e}")
            return {}
    
    async def calculate_position_betas(self, symbols: List[str]) -> Dict[str, float]:
        """Розрахунок бета-коефіцієнтів активів відносно BTC"""
        try:
            # В реальній системі це аналіз кореляції з історичними даними
            # Тут використовуємо типові бета для різних категорій
            
            betas = {}
            
            for symbol in symbols:
                if 'BTC' in symbol:
                    betas[symbol] = 1.0
                elif 'ETH' in symbol:
                    betas[symbol] = 1.3
                elif symbol in ['DIA/USDT', 'API3/USDT']:
                    betas[symbol] = 1.8  # DeFi токени більш волатильні
                elif symbol in ['PENDLE/USDT', 'RNDR/USDT']:
                    betas[symbol] = 2.2  # Yield farming і AI токени
                elif symbol in ['UMA/USDT', 'FIDA/USDT']:
                    betas[symbol] = 2.5  # Менші токени більш волатільні
                else:
                    betas[symbol] = 1.5  # Дефолт для альткоїнів
            
            logger.info(f"[DATA] Бета-коефіцієнти: {betas}")
            return betas
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка розрахунку бета: {e}")
            return {symbol: 1.5 for symbol in symbols}
    
    async def execute_hedge(self, hedge_sizes: Dict[str, float]) -> Dict[str, dict]:
        """Виконання хеджування (створення short позицій)"""
        try:
            executed_hedges = {}
            
            for symbol, size_usd in hedge_sizes.items():
                if size_usd < 10:  # Мінімальний розмір $10
                    continue
                
                try:
                    # Отримуємо поточну ціну
                    ticker = await self.exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                    
                    # Розраховуємо кількість
                    quantity = size_usd / current_price
                    
                    # Створюємо short ордер (sell)
                    # В реальності це futures позиція
                    hedge_order = await self.exchange.create_market_order(
                        symbol=symbol,
                        side='sell',  # Short позиція
                        amount=quantity,
                        params={'reduceOnly': False}  # Не reduce-only для відкриття нової позиції
                    )
                    
                    hedge_data = {
                        'order': hedge_order,
                        'symbol': symbol,
                        'side': 'short',
                        'size_usd': size_usd,
                        'quantity': quantity,
                        'entry_price': current_price,
                        'created_at': datetime.now(),
                        'status': 'active'
                    }
                    
                    self.hedge_positions[symbol] = hedge_data
                    executed_hedges[symbol] = hedge_data
                    
                    logger.info(f"[SHIELD] Хедж виконано: {symbol} short ${size_usd:,.0f} @ {current_price}")
                    
                except Exception as e:
                    logger.error(f"[ERROR] Помилка виконання хеджу {symbol}: {e}")
            
            return executed_hedges
            
        except Exception as e:
            logger.error(f"[ERROR] Критична помилка виконання хеджування: {e}")
            return {}
    
    async def close_hedge(self, symbol: str) -> bool:
        """Закриття конкретного хеджу"""
        try:
            if symbol not in self.hedge_positions:
                logger.warning(f"[WARNING] Хедж {symbol} не знайдено")
                return False
            
            hedge_data = self.hedge_positions[symbol]
            
            if hedge_data['status'] != 'active':
                return True
            
            # Створюємо зворотній ордер (buy для закриття short)
            close_order = await self.exchange.create_market_order(
                symbol=symbol,
                side='buy',  # Закриття short позиції
                amount=hedge_data['quantity'],
                params={'reduceOnly': True}  # Reduce-only для закриття
            )
            
            hedge_data['close_order'] = close_order
            hedge_data['status'] = 'closed'
            hedge_data['closed_at'] = datetime.now()
            
            # Розраховуємо P&L хеджу
            current_price = close_order['price']
            entry_price = hedge_data['entry_price']
            
            # Для short позиції: P&L = (Entry - Current) * Quantity
            pnl_usd = (entry_price - current_price) * hedge_data['quantity']
            hedge_data['pnl_usd'] = pnl_usd
            
            logger.info(f"[OK] Хедж закрито: {symbol} P&L ${pnl_usd:+,.0f}")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка закриття хеджу {symbol}: {e}")
            return False
    
    async def close_all_hedges(self) -> Dict[str, bool]:
        """Закриття всіх активних хеджів"""
        try:
            results = {}
            
            active_hedges = [
                symbol for symbol, data in self.hedge_positions.items() 
                if data['status'] == 'active'
            ]
            
            for symbol in active_hedges:
                results[symbol] = await self.close_hedge(symbol)
            
            logger.info(f"[CLEAN] Закрито {sum(results.values())}/{len(results)} хеджів")
            
            return results
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка закриття всіх хеджів: {e}")
            return {}
    
    async def rebalance_hedges(self, current_long_positions: Dict[str, float]) -> bool:
        """Ребалансування хеджів при зміні позицій"""
        try:
            if not self.hedge_active:
                return True
            
            # Розраховуємо нові розміри хеджів
            new_hedge_sizes = await self.calculate_hedge_sizes(current_long_positions)
            
            if not new_hedge_sizes:
                # Закриваємо всі хеджі якщо вони не потрібні
                await self.close_all_hedges()
                return True
            
            # Порівнюємо з поточними хеджами
            for symbol, target_size in new_hedge_sizes.items():
                current_size = 0
                if symbol in self.hedge_positions and self.hedge_positions[symbol]['status'] == 'active':
                    current_size = self.hedge_positions[symbol]['size_usd']
                
                size_diff = abs(target_size - current_size)
                threshold = target_size * 0.2  # 20% поріг для ребалансування
                
                if size_diff > threshold:
                    # Закриваємо старий хедж
                    if symbol in self.hedge_positions:
                        await self.close_hedge(symbol)
                    
                    # Створюємо новий
                    await self.execute_hedge({symbol: target_size})
                    
                    logger.info(f"[REFRESH] Ребалансовано хедж {symbol}: ${current_size:,.0f} → ${target_size:,.0f}")
            
            # Закриваємо хеджі які більше не потрібні
            for symbol in list(self.hedge_positions.keys()):
                if (symbol not in new_hedge_sizes and 
                    self.hedge_positions[symbol]['status'] == 'active'):
                    await self.close_hedge(symbol)
                    logger.info(f"[ERROR] Видалено непотрібний хедж {symbol}")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка ребалансування хеджів: {e}")
            return False
    
    async def monitor_hedge_performance(self) -> dict:
        """Моніторинг ефективності хеджування"""
        try:
            if not self.hedge_positions:
                return {'status': 'no_hedges', 'total_pnl': 0}
            
            total_pnl = 0
            active_hedges = 0
            hedge_details = {}
            
            for symbol, hedge_data in self.hedge_positions.items():
                if hedge_data['status'] == 'active':
                    # Розраховуємо unrealized P&L
                    ticker = await self.exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                    entry_price = hedge_data['entry_price']
                    
                    unrealized_pnl = (entry_price - current_price) * hedge_data['quantity']
                    total_pnl += unrealized_pnl
                    active_hedges += 1
                    
                    hedge_details[symbol] = {
                        'status': 'active',
                        'entry_price': entry_price,
                        'current_price': current_price,
                        'unrealized_pnl': unrealized_pnl,
                        'size_usd': hedge_data['size_usd']
                    }
                    
                elif 'pnl_usd' in hedge_data:
                    # Додаємо realized P&L
                    total_pnl += hedge_data['pnl_usd']
                    
                    hedge_details[symbol] = {
                        'status': 'closed',
                        'realized_pnl': hedge_data['pnl_usd']
                    }
            
            performance = {
                'timestamp': datetime.now().isoformat(),
                'hedge_active': self.hedge_active,
                'active_hedges_count': active_hedges,
                'total_pnl_usd': total_pnl,
                'last_dominance_check': self.last_dominance_check.isoformat() if self.last_dominance_check else None,
                'hedge_details': hedge_details
            }
            
            return performance
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка моніторингу хеджів: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def hedge_maintenance_cycle(self, current_positions: Dict[str, float]):
        """Основний цикл обслуговування хеджування"""
        try:
            # 1. Оновлюємо ринкові дані
            await self.update_market_data()
            
            # 2. Перевіряємо BTC dominance
            need_hedge = await self.check_btc_dominance()
            
            # 3. Ребалансуємо хеджі при необхідності
            if need_hedge and current_positions:
                await self.rebalance_hedges(current_positions)
            
            # 4. Моніторимо ефективність
            performance = await self.monitor_hedge_performance()
            
            if performance.get('total_pnl_usd', 0) != 0:
                logger.info(f"[SHIELD] Хедж P&L: ${performance['total_pnl_usd']:+,.0f}")
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка циклу обслуговування хеджів: {e}")

# Тест Hedge Manager
async def test_hedge_manager():
    """Тест без реального exchange"""
    
    class MockExchange:
        def __init__(self):
            self.prices = {'BTC/USDT': 50000, 'ETH/USDT': 3000}
            self.order_id = 1000
        
        async def fetch_ticker(self, symbol):
            return {
                'symbol': symbol,
                'last': self.prices.get(symbol, 100),
                'quoteVolume': 1000000,
                'percentage': 2.5
            }
        
        async def create_market_order(self, symbol, side, amount, params=None):
            self.order_id += 1
            return {
                'id': str(self.order_id),
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': self.prices.get(symbol, 100),
                'status': 'closed'
            }
    
    exchange = MockExchange()
    hedge_manager = HedgeManager(exchange, target_beta=0.4)
    
    # Ініціалізуємо систему
    await hedge_manager.initialize_hedge_system()
    
    # Тестуємо розрахунок хеджів
    long_positions = {
        'DIA/USDT': 5000,
        'PENDLE/USDT': 4000,
        'API3/USDT': 3000
    }
    
    hedge_sizes = await hedge_manager.calculate_hedge_sizes(long_positions)
    print(f"Розраховані хеджі: {hedge_sizes}")
    
    # Симулюємо активацію хеджу
    hedge_manager.hedge_active = True
    executed = await hedge_manager.execute_hedge(hedge_sizes)
    print(f"Виконані хеджі: {len(executed)}")
    
    # Моніторинг
    performance = await hedge_manager.monitor_hedge_performance()
    print(f"Статус хеджів: {performance['active_hedges_count']} активних")

if __name__ == "__main__":
    asyncio.run(test_hedge_manager())
