# Модуль для роботи з біржею Binance
import ccxt
import asyncio
from typing import Dict, Optional, List
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class OrderResult:
    """Результат виконання ордеру"""
    success: bool
    order_id: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None
    error: Optional[str] = None

class BinanceExchange:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        Ініціалізація підключення до Binance
        """
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': testnet,  # Тестова мережа
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'  # Для ф'ючерсів
            }
        })
        
        self.testnet = testnet
        logger.info(f"🔗 Підключення до Binance {'Testnet' if testnet else 'Mainnet'}")
    
    async def get_balance(self) -> Dict[str, float]:
        """Отримання балансу"""
        try:
            balance = await self.exchange.fetch_balance()
            return {
                'USDT': balance['USDT']['free'] if 'USDT' in balance else 0.0,
                'total': balance['USDT']['total'] if 'USDT' in balance else 0.0
            }
        except Exception as e:
            logger.error(f"Помилка отримання балансу: {e}")
            return {'USDT': 0.0, 'total': 0.0}
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Отримання поточної ціни"""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            logger.error(f"Помилка отримання ціни {symbol}: {e}")
            return None
    
    async def get_orderbook(self, symbol: str, limit: int = 100) -> Optional[Dict]:
        """Отримання стакану"""
        try:
            orderbook = await self.exchange.fetch_order_book(symbol, limit)
            return orderbook
        except Exception as e:
            logger.error(f"Помилка отримання стакану {symbol}: {e}")
            return None
    
    async def calculate_spread(self, symbol: str) -> Optional[float]:
        """Розрахунок спреду"""
        orderbook = await self.get_orderbook(symbol, 5)
        if not orderbook:
            return None
        
        best_bid = orderbook['bids'][0][0] if orderbook['bids'] else 0
        best_ask = orderbook['asks'][0][0] if orderbook['asks'] else 0
        
        if best_bid and best_ask:
            spread = ((best_ask - best_bid) / best_bid) * 100
            return spread
        return None
    
    async def get_funding_rate(self, symbol: str) -> Optional[float]:
        """Отримання funding rate"""
        try:
            funding = await self.exchange.fetch_funding_rate(symbol)
            return funding['fundingRate'] * 100  # Конвертуємо в проценти
        except Exception as e:
            logger.error(f"Помилка отримання funding rate {symbol}: {e}")
            return None
    
    async def create_market_order(self, symbol: str, side: str, amount: float, 
                                leverage: float = 1.0) -> OrderResult:
        """Створення ринкового ордеру"""
        try:
            # Встановлюємо кредитне плече
            if leverage > 1.0:
                await self.exchange.set_leverage(leverage, symbol)
            
            # Створюємо ордер
            order = await self.exchange.create_market_order(
                symbol=symbol,
                side=side,  # 'buy' або 'sell'
                amount=amount
            )
            
            logger.info(f"✅ Ордер створено: {side.upper()} {amount} {symbol} @ {order.get('price', 'Market')}")
            
            return OrderResult(
                success=True,
                order_id=order['id'],
                price=order.get('price'),
                quantity=order.get('amount')
            )
            
        except Exception as e:
            logger.error(f"Помилка створення ордеру {symbol}: {e}")
            return OrderResult(success=False, error=str(e))
    
    async def create_stop_loss_order(self, symbol: str, side: str, amount: float, 
                                   stop_price: float) -> OrderResult:
        """Створення стоп-лосс ордеру"""
        try:
            order = await self.exchange.create_order(
                symbol=symbol,
                type='stop_market',
                side=side,
                amount=amount,
                params={'stopPrice': stop_price}
            )
            
            logger.info(f"🛡️ Stop-Loss встановлено: {symbol} @ {stop_price}")
            
            return OrderResult(
                success=True,
                order_id=order['id'],
                price=stop_price,
                quantity=amount
            )
            
        except Exception as e:
            logger.error(f"Помилка створення стоп-лосс {symbol}: {e}")
            return OrderResult(success=False, error=str(e))
    
    async def create_take_profit_order(self, symbol: str, side: str, amount: float, 
                                     take_profit_price: float) -> OrderResult:
        """Створення тейк-профіт ордеру"""
        try:
            order = await self.exchange.create_order(
                symbol=symbol,
                type='take_profit_market',
                side=side,
                amount=amount,
                params={'stopPrice': take_profit_price}
            )
            
            logger.info(f"🎯 Take-Profit встановлено: {symbol} @ {take_profit_price}")
            
            return OrderResult(
                success=True,
                order_id=order['id'],
                price=take_profit_price,
                quantity=amount
            )
            
        except Exception as e:
            logger.error(f"Помилка створення тейк-профіт {symbol}: {e}")
            return OrderResult(success=False, error=str(e))
    
    async def get_open_positions(self) -> List[Dict]:
        """Отримання відкритих позицій"""
        try:
            positions = await self.exchange.fetch_positions()
            # Фільтруємо тільки відкриті позиції
            open_positions = [pos for pos in positions if pos['contracts'] > 0]
            return open_positions
        except Exception as e:
            logger.error(f"Помилка отримання позицій: {e}")
            return []
    
    async def close_position(self, symbol: str) -> OrderResult:
        """Закриття позиції"""
        try:
            positions = await self.get_open_positions()
            position = next((pos for pos in positions if pos['symbol'] == symbol), None)
            
            if not position:
                return OrderResult(success=False, error="Позиція не знайдена")
            
            side = 'sell' if position['side'] == 'long' else 'buy'
            amount = abs(position['contracts'])
            
            return await self.create_market_order(symbol, side, amount)
            
        except Exception as e:
            logger.error(f"Помилка закриття позиції {symbol}: {e}")
            return OrderResult(success=False, error=str(e))
    
    async def cancel_all_orders(self, symbol: str) -> bool:
        """Скасування всіх ордерів по символу"""
        try:
            await self.exchange.cancel_all_orders(symbol)
            logger.info(f"🗑️ Всі ордери скасовано: {symbol}")
            return True
        except Exception as e:
            logger.error(f"Помилка скасування ордерів {symbol}: {e}")
            return False
    
    async def get_24h_stats(self, symbol: str) -> Optional[Dict]:
        """Отримання 24-годинної статистики"""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return {
                'price': ticker['last'],
                'change_24h': ticker['change'],
                'change_24h_percent': ticker['percentage'],
                'volume': ticker['baseVolume'],
                'high': ticker['high'],
                'low': ticker['low']
            }
        except Exception as e:
            logger.error(f"Помилка отримання статистики {symbol}: {e}")
            return None

# Допоміжні функції для роботи з API
async def test_connection(exchange: BinanceExchange) -> bool:
    """Тестування підключення"""
    try:
        balance = await exchange.get_balance()
        logger.info(f"✅ Підключення успішне. Баланс USDT: {balance['USDT']}")
        return True
    except Exception as e:
        logger.error(f"❌ Помилка підключення: {e}")
        return False

async def get_tradable_symbols(exchange: BinanceExchange, base_currency: str = 'USDT') -> List[str]:
    """Отримання списку торгових пар"""
    try:
        markets = await exchange.exchange.fetch_markets()
        symbols = [market['symbol'] for market in markets 
                  if market['quote'] == base_currency and market['active']]
        return symbols
    except Exception as e:
        logger.error(f"Помилка отримання символів: {e}")
        return []
