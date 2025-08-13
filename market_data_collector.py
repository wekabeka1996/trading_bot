"""
Модуль для збору ринкових даних з Binance Futures
для аналізу Ensemble Trade Plan
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import numpy as np
from binance import AsyncClient
from binance.enums import *
from dotenv import load_dotenv
import json

# Завантаження змінних середовища
load_dotenv()

class NumpyEncoder(json.JSONEncoder):
    """Кастомний JSON encoder для обробки numpy типів"""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if pd.isna(obj):
            return None
        return super(NumpyEncoder, self).default(obj)

class MarketDataCollector:
    """Клас для збору та аналізу ринкових даних з Binance Futures"""
    
    def __init__(self):
        self.testnet = os.getenv('BINANCE_TESTNET', 'True').lower() == 'true'
        
        # Вибираємо правильні ключі залежно від режиму
        if self.testnet:
            self.api_key = os.getenv('BINANCE_TESTNET_API_KEY')
            self.api_secret = os.getenv('BINANCE_TESTNET_SECRET')
        else:
            self.api_key = os.getenv('BINANCE_API_KEY')
            self.api_secret = os.getenv('BINANCE_SECRET')
            
        self.client = None
        
        # Символи для аналізу згідно актуального плану 2025-08-07
        # Примітка: PEPE торгується як 1000PEPEUSDT на Binance Futures
        self.symbols = ['SUIUSDT', '1000PEPEUSDT', 'ARBUSDT', 'DOGEUSDT', 'TIAUSDT']
        # Мапінг для відображення
        self.symbol_display = {
            'SUIUSDT': 'SUIUSDT',
            '1000PEPEUSDT': 'PEPEUSDT',
            'ARBUSDT': 'ARBUSDT',
            'DOGEUSDT': 'DOGEUSDT',
            'TIAUSDT': 'TIAUSDT'
        }
        
        # Watchlist для моніторингу high-movers
        self.watchlist_symbols = ['MEMEFTUSDT', 'PLAYUSDT', 'VELVETUSDT', 'OMNIUSDT', 'LEVERUSDT', 'SPELLUSDT']
        
    async def initialize(self):
        """Ініціалізація асинхронного клієнта"""
        if self.testnet:
            self.client = await AsyncClient.create(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=True
            )
        else:
            self.client = await AsyncClient.create(
                api_key=self.api_key,
                api_secret=self.api_secret
            )
    
    async def get_current_prices(self) -> Dict[str, float]:
        """Отримання поточних цін для всіх символів"""
        prices = {}
        tickers = await self.client.futures_ticker()
        
        for ticker in tickers:
            if ticker['symbol'] in self.symbols:
                prices[ticker['symbol']] = {
                    'price': float(ticker['lastPrice']),
                    'volume_24h': float(ticker['quoteVolume']),
                    'change_24h': float(ticker['priceChangePercent'])
                }
        
        return prices
    
    async def get_funding_rates(self) -> Dict[str, float]:
        """Отримання funding rates для символів"""
        funding_rates = {}
        
        for symbol in self.symbols:
            try:
                info = await self.client.futures_mark_price(symbol=symbol)
                funding_rates[symbol] = float(info['lastFundingRate'])
            except Exception as e:
                print(f"Помилка отримання funding rate для {symbol}: {e}")
                funding_rates[symbol] = 0.0
        
        return funding_rates
    
    async def get_orderbook_depth(self, symbol: str, limit: int = 20) -> Dict:
        """Отримання глибини стакану для символу"""
        try:
            depth = await self.client.futures_order_book(symbol=symbol, limit=limit)
            
            # Розрахунок bid/ask імбалансу
            total_bid_volume = sum(float(bid[1]) for bid in depth['bids'])
            total_ask_volume = sum(float(ask[1]) for ask in depth['asks'])
            
            imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume)
            
            return {
                'bid_volume': total_bid_volume,
                'ask_volume': total_ask_volume,
                'imbalance': imbalance,
                'best_bid': float(depth['bids'][0][0]) if depth['bids'] else 0,
                'best_ask': float(depth['asks'][0][0]) if depth['asks'] else 0,
                'spread': float(depth['asks'][0][0]) - float(depth['bids'][0][0]) if depth['bids'] and depth['asks'] else 0
            }
        except Exception as e:
            print(f"Помилка отримання orderbook для {symbol}: {e}")
            return {}
    
    async def calculate_rsi(self, symbol: str, period: int = 14, interval: str = '15m') -> float:
        """Розрахунок RSI для символу"""
        try:
            # Отримання історичних свічок
            klines = await self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=period + 10
            )
            
            # Конвертація в DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 
                'volume', 'close_time', 'quote_volume', 'trades',
                'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            
            df['close'] = df['close'].astype(float)
            
            # Розрахунок RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            result = rsi.iloc[-1]
            # Обробка NaN
            if pd.isna(result):
                return 50.0
            return float(result)
        except Exception as e:
            print(f"Помилка розрахунку RSI для {symbol}: {e}")
            return 50.0
    
    async def calculate_volatility(self, symbol: str, period: int = 20, interval: str = '1h') -> float:
        """Розрахунок волатильності (стандартне відхилення)"""
        try:
            klines = await self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=period
            )
            
            closes = [float(k[4]) for k in klines]
            returns = pd.Series(closes).pct_change().dropna()
            
            if len(returns) > 0:
                volatility = returns.std() * np.sqrt(24)  # Annualized для годинних даних
                if pd.isna(volatility):
                    return 0.0
                return float(volatility)
            return 0.0
        except Exception as e:
            print(f"Помилка розрахунку волатильності для {symbol}: {e}")
            return 0.0
    
    async def check_execution_window(self) -> Dict:
        """Перевірка часового вікна для виконання угод"""
        current_time = datetime.now()
        
        # Вікно виконання: 15:00-17:30 EEST
        execution_start = current_time.replace(hour=15, minute=0, second=0, microsecond=0)
        execution_end = current_time.replace(hour=17, minute=30, second=0, microsecond=0)
        
        is_execution_time = execution_start <= current_time <= execution_end
        
        return {
            'current_time': current_time.strftime('%H:%M EEST'),
            'execution_window': '15:00-17:30 EEST',
            'is_execution_time': is_execution_time,
            'time_to_execution': str(execution_start - current_time) if current_time < execution_start else None,
            'time_remaining': str(execution_end - current_time) if current_time < execution_end else None
        }
    
    async def check_breakout_conditions(self, symbol: str, timeframe: str = '15m') -> Dict:
        """Перевірка умов для breakout згідно з планом"""
        try:
            # Отримання останніх свічок
            klines = await self.client.futures_klines(
                symbol=symbol,
                interval=timeframe,
                limit=50
            )
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 
                'volume', 'close_time', 'quote_volume', 'trades',
                'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['volume'] = df['volume'].astype(float)
            
            # Визначення рівнів підтримки/опору
            recent_high = df['high'].rolling(20).max().iloc[-1]
            recent_low = df['low'].rolling(20).min().iloc[-1]
            current_price = df['close'].iloc[-1]
            
            # Середній обсяг
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            # Momentum (Rate of Change)
            roc = ((current_price - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100
            
            return {
                'current_price': float(current_price),
                'resistance': float(recent_high),
                'support': float(recent_low),
                'price_position': float((current_price - recent_low) / (recent_high - recent_low)) if recent_high != recent_low else 0.5,
                'volume_ratio': float(volume_ratio),
                'momentum_roc': float(roc),
                'is_breakout': bool(current_price > recent_high * 0.995),
                'is_breakdown': bool(current_price < recent_low * 1.005)
            }
        except Exception as e:
            print(f"Помилка перевірки breakout для {symbol}: {e}")
            return {}
    
    async def analyze_trade_plan(self) -> Dict:
        """Комплексний аналіз для торгового плану"""
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'symbols': {}
        }
        
        # Отримання базових даних
        prices = await self.get_current_prices()
        funding_rates = await self.get_funding_rates()
        
        for symbol in self.symbols:
            display_name = self.symbol_display.get(symbol, symbol)
            print(f"Аналіз {display_name}...")
            
            symbol_data = {
                'price_data': prices.get(symbol, {}),
                'funding_rate': funding_rates.get(symbol, 0),
                'rsi': await self.calculate_rsi(symbol),
                'volatility': await self.calculate_volatility(symbol),
                'orderbook': await self.get_orderbook_depth(symbol),
                'breakout': await self.check_breakout_conditions(symbol)
            }
            
            # Коригування цін для 1000PEPE
            if symbol == '1000PEPEUSDT':
                # Ділимо ціну на 1000 для правильного відображення
                if 'price_data' in symbol_data and 'price' in symbol_data['price_data']:
                    symbol_data['price_data']['actual_price'] = symbol_data['price_data']['price'] / 1000
                if 'breakout' in symbol_data and 'current_price' in symbol_data['breakout']:
                    symbol_data['breakout']['actual_price'] = symbol_data['breakout']['current_price'] / 1000
            
            # Додаткові розрахунки для стратегій згідно плану 2025-08-07
            if symbol == 'SUIUSDT':
                current_price = symbol_data['breakout'].get('current_price', 0)
                symbol_data['strategy'] = {
                    'type': 'LONG',
                    'entry_trigger': 3.45,  # Buy-stop ≥ $3.45 (15m close)
                    'take_profit': 3.68,    # +6.7%
                    'stop_loss': 3.30,      # -4.3%
                    'probability': 0.55,
                    'leverage': 3,          # Знижено до 3×
                    'execution_window': '15:00-17:30 EEST',
                    'entry_condition_met': current_price >= 3.45,
                    'fallback_condition': 'Скасувати після 17:30 або TVL < 1.5B$'
                }
            elif symbol == '1000PEPEUSDT':
                # Для PEPE використовуємо реальні ціни (поділені на 1000)
                actual_price = symbol_data['breakout'].get('actual_price', 0)
                current_funding = symbol_data['funding_rate']
                symbol_data['strategy'] = {
                    'type': 'LONG',
                    'entry_min': 0.0000815,   # Buy-limit диапазон
                    'entry_max': 0.0000825,
                    'take_profit': 0.0000880, # +7.1%
                    'stop_loss': 0.0000760,   # -7%
                    'probability': 0.55,
                    'leverage': 3,
                    'funding_limit': 0.0012,  # ≤ 0.12%
                    'funding_risk': current_funding > 0.0012,
                    'entry_condition_met': (0.0000815 <= actual_price <= 0.0000825) and current_funding <= 0.0012,
                    'veto_condition': 'VETO if funding > 0.12%'
                }
            elif symbol == 'ARBUSDT':
                current_price = symbol_data['breakout'].get('current_price', 0)
                btc_dom = 60.4  # З плану
                symbol_data['strategy'] = {
                    'type': 'LONG',
                    'entry_trigger': 0.405,   # Buy-stop ≥ $0.405 (30m close)
                    'take_profit': 0.438,     # +8%
                    'stop_loss': 0.386,       # -4.7%
                    'probability': 0.55,
                    'leverage': 3,
                    'half_size_condition': btc_dom > 61,
                    'entry_condition_met': current_price >= 0.405,
                    'note': 'Half-size if BTC-dom > 61%'
                }
            elif symbol == 'DOGEUSDT':
                current_price = symbol_data['breakout'].get('current_price', 0)
                symbol_data['strategy'] = {
                    'type': 'SHORT',
                    'entry_trigger': 0.200,   # Sell-stop < $0.200 (5m flush)
                    'take_profit': 0.192,     # -4%
                    'stop_loss': 0.212,       # +6%
                    'probability': 0.53,
                    'leverage': 3,
                    'execution_window': '15:00-17:30 EEST',
                    'entry_condition_met': current_price <= 0.200,
                    'fallback_condition': 'Відмінити, якщо funding < 0 або соц-хайп > 2× середнього'
                }
            elif symbol == 'TIAUSDT':
                current_price = symbol_data['breakout'].get('current_price', 0)
                symbol_data['strategy'] = {
                    'type': 'CONDITIONAL_LONG',
                    'entry_trigger': 8.45,    # Buy-stop ≥ $8.45
                    'take_profit': 9.25,      # TP
                    'stop_loss': 7.90,        # SL
                    'leverage': 3,
                    'activation_condition': 'EigenLayer × Celestia партнерство підтверджено',
                    'deadline': '18:00 EEST',
                    'confirmation_requirement': 'офіційний PR або on-chain депозити > $10M',
                    'entry_condition_met': False,  # Умовна стратегія
                    'status': 'CONDITIONAL'
                }
            
            # Зберігаємо під правильним ім'ям для відображення
            analysis['symbols'][display_name] = symbol_data
        
        # Загальні ринкові метрики
        btc_data = await self.get_btc_dominance_and_metrics()
        analysis['market_metrics'] = btc_data
        
        # Перевірка часового вікна
        time_window = await self.check_execution_window()
        analysis['execution_window'] = time_window
        
        # Аналіз watchlist (high-movers)
        watchlist_data = await self.analyze_watchlist()
        analysis['watchlist'] = watchlist_data
        
        return analysis
    
    async def get_btc_dominance_and_metrics(self) -> Dict:
        """Отримання данних про домінацію BTC та ключових метрик"""
        try:
            btc_ticker = await self.client.futures_ticker(symbol='BTCUSDT')
            eth_ticker = await self.client.futures_ticker(symbol='ETHUSDT')
            
            # Розрахунок домінації (приблизно)
            btc_price = float(btc_ticker['lastPrice'])
            btc_volume = float(btc_ticker['quoteVolume'])
            
            return {
                'btc_price': btc_price,
                'btc_change_24h': float(btc_ticker['priceChangePercent']),
                'btc_dominance_estimated': 60.4,  # Базове значення з плану
                'eth_price': float(eth_ticker['lastPrice']),
                'eth_change_24h': float(eth_ticker['priceChangePercent']),
                'btc_volume_24h': btc_volume,
                'macro_data_time': '14:30 EEST',
                'execution_window': '15:00-17:30 EEST'
            }
        except Exception as e:
            print(f"Помилка отримання BTC метрик: {e}")
            return {}
    
    async def analyze_watchlist(self) -> Dict:
        """Аналіз high-movers з watchlist"""
        watchlist_analysis = {}
        
        try:
            # Отримання тікерів для watchlist
            tickers = await self.client.futures_ticker()
            ticker_dict = {ticker['symbol']: ticker for ticker in tickers}
            
            for symbol in self.watchlist_symbols:
                if symbol in ticker_dict:
                    ticker = ticker_dict[symbol]
                    
                    # Перевірка обсягу > 50M USDT
                    volume_24h = float(ticker['quoteVolume'])
                    if volume_24h >= 50_000_000:  # 50M USDT
                        
                        # Отримання funding rate
                        try:
                            funding_info = await self.client.futures_mark_price(symbol=symbol)
                            funding_rate = float(funding_info['lastFundingRate'])
                        except:
                            funding_rate = 0.0
                        
                        watchlist_analysis[symbol] = {
                            'price': float(ticker['lastPrice']),
                            'change_24h': float(ticker['priceChangePercent']),
                            'volume_24h': volume_24h,
                            'funding_rate': funding_rate,
                            'eligible_for_trading': funding_rate <= 0.0015,  # ≤ 0.15%
                            'risk_level': 'HIGH' if funding_rate > 0.001 else 'MEDIUM' if funding_rate > 0.0005 else 'LOW'
                        }
            
            return watchlist_analysis
            
        except Exception as e:
            print(f"Помилка аналізу watchlist: {e}")
            return {}
    
    async def close(self):
        """Закриття клієнта"""
        if self.client:
            await self.client.close_connection()
    
    async def export_to_json(self, data: Dict, filename: Optional[str] = None):
        """Експорт даних у JSON файл"""
        if filename is None:
            filename = f"market_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = os.path.join('c:\\trading_bot', 'data', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Використовуємо кастомний encoder для numpy типів
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, cls=NumpyEncoder)
        
        print(f"Дані збережено у {filepath}")
        return filepath

async def main():
    """Головна функція для запуску аналізу"""
    collector = MarketDataCollector()
    
    try:
        print("🔄 Ініціалізація з'єднання з Binance...")
        await collector.initialize()
        
        print("📊 Збір ринкових даних для аналізу торгового плану...")
        analysis = await collector.analyze_trade_plan()
        
        # Виведення ключових метрик
        print("\n📈 ENSEMBLE TRADE PLAN 2025-08-07 - РЕЗУЛЬТАТИ АНАЛІЗУ:")
        print("=" * 60)
        
        # Часове вікно
        if 'execution_window' in analysis:
            window = analysis['execution_window']
            print(f"\n⏰ ЧАСОВЕ ВІКНО:")
            print(f"  Поточний час: {window.get('current_time', 'N/A')}")
            print(f"  Вікно виконання: {window.get('execution_window', 'N/A')}")
            print(f"  Статус: {'✅ АКТИВНЕ' if window.get('is_execution_time', False) else '❌ НЕАКТИВНЕ'}")
            if window.get('time_to_execution'):
                print(f"  До відкриття: {window['time_to_execution']}")
            if window.get('time_remaining'):
                print(f"  Залишилось часу: {window['time_remaining']}")
        
        # Ринкові метрики
        if 'market_metrics' in analysis:
            metrics = analysis['market_metrics']
            print(f"\n📊 РИНКОВІ МЕТРИКИ:")
            print(f"  BTC: ${metrics.get('btc_price', 0):,.2f} ({metrics.get('btc_change_24h', 0):+.2f}%)")
            print(f"  BTC Dominance: {metrics.get('btc_dominance_estimated', 0):.1f}%")
            print(f"  Макродані: {metrics.get('macro_data_time', 'N/A')}")
        
        print(f"\n💰 ОСНОВНІ СТРАТЕГІЇ (Leverage: 3×):")
        print("-" * 50)
        
        for symbol, data in analysis['symbols'].items():
            print(f"\n{symbol}:")
            
            # Визначаємо яку ціну показувати
            if symbol == 'PEPEUSDT' and 'actual_price' in data.get('price_data', {}):
                price = data['price_data']['actual_price']
            else:
                price = data['price_data'].get('price', 0)
            
            print(f"  Ціна: ${price:.8f}")
            print(f"  Зміна 24h: {data['price_data'].get('change_24h', 0):.2f}%")
            print(f"  Обсяг 24h: ${data['price_data'].get('volume_24h', 0):,.0f}")
            print(f"  RSI: {data['rsi']:.2f}")
            print(f"  Funding Rate: {data['funding_rate']:.4%}")
            print(f"  Волатильність: {data['volatility']:.2%}")
            
            if 'strategy' in data:
                strategy = data['strategy']
                strategy_type = strategy.get('type', 'N/A')
                
                print(f"  📍 Стратегія: {strategy_type}")
                
                # Різна логіка виведення залежно від типу стратегії
                if strategy_type == 'CONDITIONAL_LONG':
                    print(f"     Статус: {strategy.get('status', 'ACTIVE')}")
                    print(f"     Умова: {strategy.get('activation_condition', 'N/A')}")
                    print(f"     Дедлайн: {strategy.get('deadline', 'N/A')}")
                    print(f"     Entry: ${strategy.get('entry_trigger', 0):.8f}")
                else:
                    # Для PEPE використовуємо діапазон entry
                    if 'entry_min' in strategy and 'entry_max' in strategy:
                        print(f"     Entry: ${strategy['entry_min']:.8f}-${strategy['entry_max']:.8f}")
                    else:
                        print(f"     Entry: ${strategy.get('entry_trigger', 0):.8f}")
                
                print(f"     TP: ${strategy.get('take_profit', 0):.8f} | SL: ${strategy.get('stop_loss', 0):.8f}")
                
                if 'probability' in strategy:
                    print(f"     Ймовірність: {strategy['probability']:.0%}")
                
                print(f"     Leverage: {strategy.get('leverage', 1)}×")
                
                entry_met = strategy.get('entry_condition_met', False)
                print(f"     Умова входу: {'✅ Виконана' if entry_met else '❌ Не виконана'}")
                
                # Додаткові умови та попередження
                if 'funding_risk' in strategy and strategy['funding_risk']:
                    print(f"     ⚠️ FUNDING RISK: {strategy.get('veto_condition', 'High funding rate')}")
                
                if 'half_size_condition' in strategy:
                    print(f"     ℹ️ {strategy.get('note', 'Special condition applies')}")
                
                if 'fallback_condition' in strategy:
                    print(f"     ⚡ Fallback: {strategy['fallback_condition']}")
                
                if 'execution_window' in strategy:
                    print(f"     🕐 Вікно: {strategy['execution_window']}")
        
        # Watchlist
        if 'watchlist' in analysis and analysis['watchlist']:
            print(f"\n👀 WATCHLIST (High-Movers > 50M USDT):")
            print("-" * 40)
            
            for symbol, data in analysis['watchlist'].items():
                eligible = "✅" if data.get('eligible_for_trading', False) else "❌"
                risk = data.get('risk_level', 'UNKNOWN')
                print(f"  {symbol}: ${data.get('price', 0):.6f} ({data.get('change_24h', 0):+.1f}%) "
                      f"Vol: ${data.get('volume_24h', 0)/1_000_000:.0f}M "
                      f"Fund: {data.get('funding_rate', 0):.3%} "
                      f"Risk: {risk} {eligible}")
        
        print(f"\n📋 ПЛАН ДІЙ:")
        print("  1. Очікування макроданих о 14:30 EEST")
        print("  2. Вікно торгівлі: 15:00-17:30 EEST") 
        print("  3. Максимальний VaR портфеля: ≤ 3%")
        print("  4. OCO-ордери після відкриття позицій")
        print("  5. BTC dump > 3% → закрити всі LONG, залишити DOGE SHORT")
        
        # Збереження у файл
        await collector.export_to_json(analysis)
        
        print("\n✅ Аналіз завершено!")
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
    finally:
        await collector.close()

if __name__ == "__main__":
    asyncio.run(main())
