# Модуль для отримання ринкових даних з різних джерел
import aiohttp
import asyncio
import logging
from typing import Dict, Optional, List
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class MarketDataProvider:
    def __init__(self, config: Dict):
        """
        Ініціалізація провайдера ринкових даних
        """
        self.config = config
        self.session = None
        
        # API endpoints
        self.endpoints = {
            'coingecko': 'https://api.coingecko.com/api/v3',
            'binance': 'https://api.binance.com/api/v3',
            'fear_greed': 'https://api.alternative.me/fng/',
            'nasdaq': 'https://api.nasdaq.com/api/quote/NVDA/info'
        }
        
        logger.info("[DATA] Ініціалізація провайдера ринкових даних")
    
    async def __aenter__(self):
        """Асинхронний контекст менеджер - вхід"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронний контекст менеджер - вихід"""
        if self.session:
            await self.session.close()
    
    async def get_btc_dominance(self) -> Optional[float]:
        """Отримання BTC домінації"""
        try:
            url = f"{self.endpoints['coingecko']}/global"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    dominance = data['data']['market_cap_percentage']['btc']
                    logger.debug(f"BTC домінація: {dominance:.2f}%")
                    return dominance
        except Exception as e:
            logger.error(f"Помилка отримання BTC домінації: {e}")
        return None
    
    async def get_fear_greed_index(self) -> Optional[Dict]:
        """Отримання індексу страху та жадібності"""
        try:
            url = self.endpoints['fear_greed']
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    index_data = data['data'][0]
                    result = {
                        'value': int(index_data['value']),
                        'classification': index_data['value_classification'],
                        'timestamp': index_data['timestamp']
                    }
                    logger.debug(f"Fear & Greed: {result['value']} ({result['classification']})")
                    return result
        except Exception as e:
            logger.error(f"Помилка отримання Fear & Greed: {e}")
        return None
    
    async def get_funding_rates(self, symbols: List[str]) -> Dict[str, float]:
        """Отримання funding rates з Binance"""
        funding_rates = {}
        
        for symbol in symbols:
            try:
                url = f"{self.endpoints['binance']}/fapi/v1/premiumIndex"
                params = {'symbol': symbol}
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        funding_rate = float(data['lastFundingRate']) * 100  # Конвертуємо в проценти
                        funding_rates[symbol] = funding_rate
                        logger.debug(f"Funding rate {symbol}: {funding_rate:.4f}%")
            except Exception as e:
                logger.error(f"Помилка отримання funding rate {symbol}: {e}")
                funding_rates[symbol] = 0.0
        
        return funding_rates
    
    async def get_price(self, symbol: str) -> Optional[float]:
        """Отримання поточної ціни"""
        try:
            url = f"{self.endpoints['binance']}/ticker/price"
            params = {'symbol': symbol}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data['price'])
                    return price
        except Exception as e:
            logger.error(f"Помилка отримання ціни {symbol}: {e}")
        return None
    
    async def get_24h_ticker(self, symbol: str) -> Optional[Dict]:
        """Отримання 24-годинної статистики"""
        try:
            url = f"{self.endpoints['binance']}/ticker/24hr"
            params = {'symbol': symbol}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'symbol': data['symbol'],
                        'price': float(data['lastPrice']),
                        'change_24h': float(data['priceChange']),
                        'change_24h_percent': float(data['priceChangePercent']),
                        'volume': float(data['volume']),
                        'high': float(data['highPrice']),
                        'low': float(data['lowPrice'])
                    }
        except Exception as e:
            logger.error(f"Помилка отримання 24h ticker {symbol}: {e}")
        return None
    
    async def get_orderbook_depth(self, symbol: str, limit: int = 100) -> Optional[Dict]:
        """Отримання глибини ордербука"""
        try:
            url = f"{self.endpoints['binance']}/depth"
            params = {'symbol': symbol, 'limit': limit}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Розрахунок ліквідності
                    bids = [[float(x[0]), float(x[1])] for x in data['bids']]
                    asks = [[float(x[0]), float(x[1])] for x in data['asks']]
                    
                    if bids and asks:
                        best_bid = bids[0][0]
                        best_ask = asks[0][0]
                        spread = ((best_ask - best_bid) / best_bid) * 100
                        
                        # Ліквідність в межах 1% від mid price
                        mid_price = (best_bid + best_ask) / 2
                        bid_liquidity = sum([qty for price, qty in bids if price >= mid_price * 0.99])
                        ask_liquidity = sum([qty for price, qty in asks if price <= mid_price * 1.01])
                        
                        return {
                            'symbol': symbol,
                            'best_bid': best_bid,
                            'best_ask': best_ask,
                            'spread_percent': spread,
                            'bid_liquidity': bid_liquidity,
                            'ask_liquidity': ask_liquidity,
                            'total_liquidity': bid_liquidity + ask_liquidity
                        }
        except Exception as e:
            logger.error(f"Помилка отримання глибини {symbol}: {e}")
        return None
    
    async def get_nvidia_price_change(self) -> Optional[float]:
        """Отримання зміни ціни NVIDIA (для RNDR корелації)"""
        try:
            # Використовуємо Yahoo Finance API (безкоштовний)
            url = "https://query1.finance.yahoo.com/v8/finance/chart/NVDA"
            params = {
                'range': '1d',
                'interval': '1d'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    chart = data['chart']['result'][0]
                    meta = chart['meta']
                    
                    current_price = meta['regularMarketPrice']
                    previous_close = meta['previousClose']
                    
                    change_percent = ((current_price - previous_close) / previous_close) * 100
                    
                    logger.debug(f"NVIDIA зміна: {change_percent:+.2f}%")
                    return change_percent
        except Exception as e:
            logger.error(f"Помилка отримання NVIDIA ціни: {e}")
        return None
    
    async def get_macro_events_schedule(self) -> List[Dict]:
        """Отримання розкладу макроекономічних подій"""
        # Статичний розклад для 21-22 липня 2025
        events = [
            {
                'time': '18:00',
                'event': 'powell_speech',
                'description': 'Виступ голови ФРС Джерома Пауела',
                'impact': 'HIGH',
                'currency': 'USD'
            },
            {
                'time': '20:30',
                'event': 'pmi_usa',
                'description': 'Публікація PMI США',
                'impact': 'MEDIUM',
                'currency': 'USD'
            },
            {
                'time': '09:00',
                'event': 'ecb_opening',
                'description': 'Відкриття Європейського центрального банку',
                'impact': 'MEDIUM',
                'currency': 'EUR'
            }
        ]
        
        return events
    
    async def get_market_sentiment(self) -> Optional[Dict]:
        """Комплексна оцінка ринкових настроїв"""
        try:
            # Збираємо всі індикатори
            btc_dominance = await self.get_btc_dominance()
            fear_greed = await self.get_fear_greed_index()
            
            # Аналіз funding rates для основних альткоїнів
            alt_symbols = ['ETHUSDT', 'ADAUSDT', 'SOLUSDT', 'DOTUSDT']
            funding_rates = await self.get_funding_rates(alt_symbols)
            avg_funding = sum(funding_rates.values()) / len(funding_rates) if funding_rates else 0
            
            # Розрахунок загального настрою
            sentiment_score = 50  # Нейтральний базовий рівень
            
            if btc_dominance:
                if btc_dominance > 65:
                    sentiment_score -= 10  # Втеча в якість
                elif btc_dominance < 55:
                    sentiment_score += 10  # Альт-сезон
            
            if fear_greed:
                fg_value = fear_greed['value']
                if fg_value > 75:
                    sentiment_score += 15  # Екстремальна жадібність
                elif fg_value < 25:
                    sentiment_score -= 15  # Екстремальний страх
            
            if abs(avg_funding) > 0.1:
                sentiment_score -= 5  # Високі funding rates = перегрів
            
            # Класифікація
            if sentiment_score >= 70:
                sentiment = "EXTREMELY_BULLISH"
            elif sentiment_score >= 55:
                sentiment = "BULLISH"
            elif sentiment_score >= 45:
                sentiment = "NEUTRAL"
            elif sentiment_score >= 30:
                sentiment = "BEARISH"
            else:
                sentiment = "EXTREMELY_BEARISH"
            
            return {
                'sentiment': sentiment,
                'score': sentiment_score,
                'btc_dominance': btc_dominance,
                'fear_greed': fear_greed,
                'avg_funding_rate': avg_funding,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Помилка аналізу настроїв: {e}")
        return None
    
    async def check_liquidity_risk(self, symbol: str) -> Optional[Dict]:
        """Перевірка ризиків ліквідності"""
        depth_data = await self.get_orderbook_depth(symbol, 50)
        ticker_data = await self.get_24h_ticker(symbol)
        
        if not depth_data or not ticker_data:
            return None
        
        # Критерії ризику
        high_spread = depth_data['spread_percent'] > 0.15
        low_liquidity = depth_data['total_liquidity'] < 100000  # $100k
        low_volume = ticker_data['volume'] < 1000000  # 1M USDT за добу
        
        risk_level = "LOW"
        if high_spread and low_liquidity:
            risk_level = "EXTREME"
        elif high_spread or low_liquidity or low_volume:
            risk_level = "HIGH"
        elif depth_data['spread_percent'] > 0.1:
            risk_level = "MEDIUM"
        
        return {
            'symbol': symbol,
            'risk_level': risk_level,
            'spread_percent': depth_data['spread_percent'],
            'liquidity_usd': depth_data['total_liquidity'] * depth_data['best_bid'],
            'volume_24h': ticker_data['volume'],
            'recommendations': {
                'use_limit_orders': high_spread,
                'split_large_orders': low_liquidity,
                'avoid_market_orders': risk_level == "EXTREME"
            }
        }

# Глобальний провайдер для використання в інших модулях
market_data_provider = None

async def initialize_market_data(config: Dict):
    """Ініціалізація глобального провайдера"""
    global market_data_provider
    market_data_provider = MarketDataProvider(config)

async def get_global_market_data():
    """Отримання глобального провайдера"""
    if not market_data_provider:
        raise RuntimeError("Market data provider не ініціалізовано")
    return market_data_provider

# Тестування провайдера
async def test_market_data():
    """Тестування всіх функцій провайдера"""
    config = {'data_sources': {}}
    
    async with MarketDataProvider(config) as provider:
        logger.info("🧪 Тестування провайдера ринкових даних...")
        
        # Тест BTC домінації
        dominance = await provider.get_btc_dominance()
        logger.info(f"BTC домінація: {dominance}%")
        
        # Тест Fear & Greed
        fg = await provider.get_fear_greed_index()
        logger.info(f"Fear & Greed: {fg}")
        
        # Тест funding rates
        funding = await provider.get_funding_rates(['BTCUSDT', 'ETHUSDT'])
        logger.info(f"Funding rates: {funding}")
        
        # Тест настроїв ринку
        sentiment = await provider.get_market_sentiment()
        logger.info(f"Настрій ринку: {sentiment}")
        
        logger.info("[OK] Тестування завершено")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_market_data())
