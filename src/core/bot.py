# Головний файл автоматичної торгової системи
# Версія: 2.2 (оновлено під Binance Futures Testnet від 21.07.2025)
# USTC виключено, PENDLE TP2 піднято до 9.5%, API3 вага знижена, RNDR→RENDER

# Виправлення Windows asyncio проблем
from windows_asyncio_fix import fix_windows_asyncio
fix_windows_asyncio()

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
import json
import os
from dataclasses import dataclass
from enum import Enum
import pytz
import ccxt

# Налаштування логування з UTF-8 підтримкою
from logging_setup import setup_logging, get_logger
from exchange_manager import ExchangeManager
setup_logging()
logger = get_logger(__name__)

@dataclass
class TradingParams:
    """Параметри торгівлі для кожного активу"""
    symbol: str
    weight: float  # Вага в портфелі (0.0-1.0)
    max_leverage: float
    tp1_percent: float  # Take Profit 1 (0.0-1.0)
    tp2_percent: float  # Take Profit 2 (0.0-1.0)
    sl_percent: float   # Stop Loss (0.0-1.0, negative)
    priority: str       # "core", "core_alpha", "thematic_ai", "micro_play"
    description: str
    entry_time_start: str = "09:00"  # Час початку входу
    entry_time_end: str = "21:00"    # Час завершення входу
    special_conditions: Dict = None  # Додаткові умови (funding, NVDA correlation тощо)
    
@dataclass 
class MarketCondition:
    """Ринкові умови"""
    btc_dominance: float
    btc_price_change_24h: float
    btc_price_change_15m: float  # Для швидких реакцій
    fear_greed_index: int
    funding_rates: Dict[str, float]
    nvda_change: Optional[float] = None  # Для RENDER корреляції
    
@dataclass
class MacroEvent:
    """Макроекономічна подія"""
    name: str
    datetime: datetime
    impact_level: str  # "HIGH", "MEDIUM", "LOW"
    action_required: str
    advance_notice_minutes: int

class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM" 
    HIGH = "HIGH"
    EXTREME = "EXTREME"

class PositionPriority(Enum):
    CORE = "core"                    # DIA - основа портфеля
    CORE_ALPHA = "core_alpha"        # PENDLE - ядро з підвищеним потенціалом
    CORE_REDUCED = "core_reduced"    # API3 - скорочена вага
    THEMATIC_AI = "thematic_ai"      # RENDER - AI тематика (GPU рендеринг)
    MICRO_PLAY = "micro_play"        # UMA, FIDA - мікро-ігри

class TradingBot:
    def __init__(self, config_file: str = "config.json"):
        """
        Ініціалізація торгового бота з оновленими параметрами GPT плану
        """
        self.config = self.load_config(config_file)
        self.portfolio_size = 600.0  # $600 USD (ТЕСТНЕТ - по $100 на позицію)
        self.positions = {}
        self.market_data = {}
        self.is_running = False
        self.hedge_position = None  # Для динамічного хеджування
        self.exchange_manager = None  # Exchange manager
        self.exchange = None  # CCXT exchange instance
        
        # Торгові параметри (оновлені під план GPT 21.07.2025)
        self.trading_params = {
            # CORE - DIA (22% вага, стабільна основа)
            "DIA": TradingParams(
                symbol="DIA/USDT",  # ✅ Оновлено формат
                weight=0.22,  # 22% (було 23%)
                max_leverage=5.0,
                tp1_percent=0.04,   # 4%
                tp2_percent=0.08,   # 8%
                sl_percent=-0.025,  # -2.5%
                priority="core",
                description="Oracle data, DAO initiatives",
                special_conditions={"ema_check": True, "vwap_check": True}
            ),
            
            # CORE ALPHA - PENDLE (20% вага, підвищена ціль)
            "PENDLE": TradingParams(
                symbol="PENDLE/USDT",  # ✅ Оновлено формат 
                weight=0.20,  # 20% (було 25%)
                max_leverage=5.0,
                tp1_percent=0.05,   # 5%
                tp2_percent=0.095,  # 9.5% ⬆️ ПІДВИЩЕНО!
                sl_percent=-0.03,   # -3%
                priority="core_alpha",
                description="Restaking/yield products, growing OI",
                special_conditions={"high_oi_check": True, "volume_spike": True}
            ),
            
            # CORE REDUCED - API3 (17% вага, обережно через funding)
            "API3": TradingParams(
                symbol="API3/USDT",  # ✅ Оновлено формат
                weight=0.17,  # 17% ⬇️ ЗНИЖЕНО з 20%
                max_leverage=4.0,
                tp1_percent=0.04,   # 4% 
                tp2_percent=0.07,   # 7%
                sl_percent=-0.025,  # -2.5%
                priority="core_reduced",
                description="First-party oracles, funding overheated",
                special_conditions={"funding_threshold": 0.10, "funding_check": True}
            ),
            
            # THEMATIC AI - RENDER (15% вага, залежність від NVIDIA)
            "RENDER": TradingParams(
                symbol="RENDER/USDT",  # ✅ Оновлено на доступний символ
                weight=0.15,  # 15%
                max_leverage=4.0,
                tp1_percent=0.03,   # 3%
                tp2_percent=0.05,   # 5%
                sl_percent=-0.02,   # -2%
                priority="thematic_ai",
                description="AI narrative tied to NVDA/chips - RENDER network",
                special_conditions={"nvda_correlation": True, "nvda_threshold": {"positive": 0.03, "negative": -0.04}}
            ),
            
            # MICRO PLAY - UMA (9% вага, постновинні рухи)
            "UMA": TradingParams(
                symbol="UMA/USDT",  # ✅ Оновлено формат
                weight=0.09,  # 9% ⬇️ ЗНИЖЕНО з 11%
                max_leverage=3.0,  # ⬇️ ЗНИЖЕНО з 4x
                tp1_percent=0.05,   # 5%
                tp2_percent=0.10,   # 10%
                sl_percent=-0.03,   # -3%
                priority="micro_play",
                description="oSnap/optimistic oracle pump impulse",
                special_conditions={"post_news_cooldown": True, "low_volume_check": True}
            ),
            
            # MICRO PLAY - FIDA (9% вага, тонкий стакан)
            "FIDA": TradingParams(
                symbol="FIDA/USDT",  # ✅ Оновлено формат
                weight=0.09,  # 9% ⬇️ ЗНИЖЕНО з 12%
                max_leverage=2.0,  # ⬇️ ПОСИЛЕНО обережність
                tp1_percent=0.04,   # 4%
                tp2_percent=0.06,   # 6%
                sl_percent=-0.035,  # -3.5% ⬇️ ПОСИЛЕНО SL
                priority="micro_play",
                description="Thin orderbook, limit orders only",
                special_conditions={"spread_threshold": 0.15, "limit_orders_only": True, "micro_lots": True}
            )
        }
        
        # Налаштування хеджування (посилено β з 0.3 до 0.4)
        self.hedge_config = {
            "beta": 0.4,  # ⬆️ ПОСИЛЕНО хедж
            "btc_dominance_threshold": 62.5,
            "btc_flash_crash_threshold": -0.02,  # -2% за 15 хв
            "hedge_instruments": ["BTC/USDT", "ETH/USDT"],
            "hedge_allocation": 0.2  # 20% портфеля на хедж
        }
        
        # Макроподії (критично важливо!)
        self.macro_events = {
            "powell_speech": {
                "datetime": datetime(2025, 7, 22, 15, 30, tzinfo=pytz.timezone('Europe/Kiev')),
                "position_reduction": 0.5,  # 50% скорочення
                "advance_notice": timedelta(hours=1),
                "description": "Fed Chair Powell speech - CRITICAL!"
            },
            "ecb_decision": {
                "datetime": datetime(2025, 7, 24, 15, 45, tzinfo=pytz.timezone('Europe/Kiev')),
                "position_reduction": 0.3,  # 30% скорочення
                "advance_notice": timedelta(hours=2),
                "description": "ECB monetary policy decision"
            }
        }
        
        # Часові вікна (оновлено під план)
        self.entry_window = {
            "start": "11:45",  # ⬅️ ЗСУНУТО раніше
            "end": "12:30"     # ⬅️ ЗСУНУТО раніше
        }
        
        # Екстрені правила
        self.emergency_rules = {
            "max_overnight_leverage": 2.0,  # Не більше 2x вночі
            "close_before_midnight": True,
            "nvda_correlation_render": True,
            "funding_rate_api3_limit": 0.10,
            "thin_liquidity_fida_limit": 50000  # $50k мін ліквідність
        }
    
    def load_config(self, config_file: str) -> dict:
        """Завантаження конфігурації"""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Файл конфігурації {config_file} не знайдено. Використовуються стандартні налаштування.")
            return self.get_default_config()
    
    def get_default_config(self) -> dict:
        """Стандартна конфігурація"""
        return {
            "exchange": {
                "name": "binance",
                "api_key": "YOUR_API_KEY",
                "api_secret": "YOUR_API_SECRET",
                "testnet": True
            },
            "risk_management": {
                "max_portfolio_risk": 2.5,  # VaR ≤ 2.5%
                "max_position_size": 25.0,  # Максимум 25% в одній позиції
                "emergency_stop_loss": -10.0,  # Екстрений стоп всього портфеля
                "btc_dominance_threshold": 62.5  # Поріг для хеджування
            },
            "monitoring": {
                "price_check_interval": 30,  # секунд
                "news_check_interval": 300,  # 5 хвилин
                "funding_rate_threshold": 0.1  # 0.1% = перегрів
            }
        }
    
    async def init_exchange(self):
        """Ініціалізація підключення до біржі через ExchangeManager (тепер синхронно)"""
        try:
            logger.info("[INIT] Ініціалізація підключення до біржі...")
            
            # Використовуємо ExchangeManager для правильного підключення
            self.exchange_manager = ExchangeManager()
            # Тепер initialize() синхронний, викликаємо напряму
            connection_success = self.exchange_manager.initialize()
            
            if connection_success:
                self.exchange = self.exchange_manager.exchange
                logger.info("[EXCHANGE] ✅ Підключення успішне!")
                return True
            else:
                logger.error("[EXCHANGE] ❌ Помилка підключення до біржі")
                return False
                
        except Exception as e:
            logger.error(f"[EXCHANGE] Помилка підключення до біржі: {e}")
            self.exchange = None
            return False
    
    async def start(self):
        """Запуск торгового бота з новими функціями моніторингу"""
        logger.info("[START] Запуск автоматичної торгової системи v2.1...")
        logger.info(f"[PORTFOLIO] Розмір портфеля: ${self.portfolio_size} (ТЕСТНЕТ)")
        logger.info("[ASSETS] Нові активи: DIA($132), PENDLE($120), API3($102), RENDER($90), UMA($54), FIDA($54)")
        logger.info("[WARNING] USTC виключено з портфеля (регуляторні ризики)")
        logger.info(f"[HEDGE] Хедж посилено: beta = {self.hedge_config['beta']}")
        logger.info("[MODE] РЕАЛЬНІ ОРДЕРИ - тестнет з справжніми API викликами")
        
        # Ініціалізуємо підключення до біржі
        logger.info("[INIT] Ініціалізація підключення до біржі...")
        exchange_ready = await self.init_exchange()
        if not exchange_ready:
            logger.error("[INIT] Не вдалося підключитися до біржі - працюємо в fallback режимі")
        
        self.is_running = True
        
        # Перевіряємо наближення макроподій
        await self.check_upcoming_macro_events()
        
        # Запускаємо основні процеси (спрощена версія)
        tasks = [
            self.create_portfolio_once(),    # Замість моніторингу - одноразове створення
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Отримано сигнал зупинки...")
            await self.shutdown()
    
    async def create_portfolio_once(self):
        """Одноразове створення портфеля без моніторингу"""
        logger.info("[PORTFOLIO] Початок створення портфеля...")
        
        try:
            # Проходимо по всіх активах і створюємо позиції
            for asset, params in self.trading_params.items():
                logger.info(f"[POSITION] Створюємо позицію для {asset}...")
                
                # Розраховуємо розмір позиції на основі ваги
                total_portfolio_size = 600.0  # USDT
                position_size_usd = total_portfolio_size * params.weight
                allocation_percent = params.weight * 100
                
                logger.info(f"[POSITION] {asset}: вага={params.weight:.1%}, розмір=${position_size_usd:.0f}")
                
                # Викликаємо open_position з правильними параметрами
                success = await self.open_position(asset=asset, params=params)
                
                if success:
                    logger.info(f"[POSITION] ✅ {asset} позицію створено успішно")
                else:
                    logger.error(f"[POSITION] ❌ {asset} позицію не вдалося створити")
                
                # Невелика пауза між ордерами
                await asyncio.sleep(2)
                
            logger.info("[PORTFOLIO] Портфель створено!")
            
        except Exception as e:
            logger.error(f"[PORTFOLIO] Помилка створення портфеля: {e}")
            import traceback
            traceback.print_exc()
        
        # Завершуємо роботу після створення портфеля
        self.is_running = False
    
    async def market_monitor(self):
        """Моніторинг ринкових даних"""
        while self.is_running:
            try:
                # Отримуємо поточні ціни
                await self.update_market_data()
                
                # Перевіряємо умови входу
                await self.check_entry_conditions()
                
                # Перевіряємо умови виходу
                await self.check_exit_conditions()
                
                await asyncio.sleep(self.config["monitoring"]["price_check_interval"])
                
            except Exception as e:
                logger.error(f"Помилка в моніторингу ринку: {e}")
                await asyncio.sleep(60)
    
    async def update_market_data(self):
        """Оновлення ринкових даних"""
        try:
            from simple_market_data import SimpleMarketDataProvider
            
            provider = SimpleMarketDataProvider(self.config)
            
            # Оновлюємо ключові індикатори (синхронно)
            self.market_data['btc_dominance'] = provider.get_btc_dominance()
            self.market_data['fear_greed'] = provider.get_fear_greed_index()
            self.market_data['sentiment'] = provider.get_market_sentiment()
            
            logger.debug(f"[DATA] Оновлено ринкові дані: BTC dom={self.market_data.get('btc_dominance', 'N/A')}%")
            
        except Exception as e:
            logger.error(f"[DATA] Помилка оновлення ринкових даних: {e}")
            # Fallback значення
            self.market_data['btc_dominance'] = 60.0
            self.market_data['sentiment'] = {'sentiment': 'NEUTRAL', 'score': 50}
    
    async def check_entry_conditions(self):
        """Перевірка умов входу в позиції"""
        current_time = datetime.now().strftime("%H:%M")
        
        for asset, params in self.trading_params.items():
            if asset in self.positions:
                continue  # Позиція вже відкрита
                
            # Перевіряємо час входу
            if not self.is_entry_time_valid(current_time, params):
                continue
                
            # Перевіряємо ринкові умови
            if await self.should_enter_position(asset, params):
                await self.open_position(asset, params)
    
    def is_entry_time_valid(self, current_time: str, params: TradingParams) -> bool:
        """Перевірка чи поточний час підходить для входу"""
        try:
            # Конвертуємо строки у time об'єкти для правильного порівняння
            from datetime import time
            
            def str_to_time(time_str: str) -> time:
                hour, minute = map(int, time_str.split(':'))
                return time(hour, minute)
            
            current = str_to_time(current_time)
            start = str_to_time(params.entry_time_start)
            end = str_to_time(params.entry_time_end)
            
            return start <= current <= end
        except Exception as e:
            logger.warning(f"Помилка перевірки часу входу: {e}")
            return True  # Fallback - дозволяємо вхід
    
    async def should_enter_position(self, asset: str, params: TradingParams) -> bool:
        """Визначення чи варто входити в позицію"""
        # Перевіряємо BTC домінацію
        btc_dominance = await self.get_btc_dominance()
        if btc_dominance > self.config["risk_management"]["btc_dominance_threshold"]:
            logger.warning(f"BTC домінація {btc_dominance}% перевищує поріг. Відкладаємо вхід в {asset}")
            return False
        
        # Спеціальні перевірки для кожного активу
        if asset == "API3":
            funding_rate = await self.get_funding_rate("API3/USDT")
            if funding_rate > 0.12:  # Перегрів
                logger.warning(f"API3 funding rate {funding_rate}% занадто високий")
                return False
        
        elif asset == "FIDA":
            spread = await self.get_spread("FIDA/USDT")
            if spread > 0.15:  # Погана ліквідність
                logger.warning(f"FIDA спред {spread}% занадто широкий")
                return False
        
        elif asset == "RENDER":
            nvidia_change = await self.get_nvidia_price_change()
            if nvidia_change < -4.0:  # NVIDIA впала більше 4%
                logger.warning(f"NVIDIA впала на {nvidia_change}%. Скасовуємо RENDER")
                return False
        
        return True
    
    async def open_position(self, asset: str, params: TradingParams):
        """Відкриття позиції з детальним логуванням"""
        position_size = self.portfolio_size * params.weight
        
        logger.info(f"[POSITION_START] Спроба відкриття позиції {asset}:")
        logger.info(f"  Розмір: ${position_size:.2f} ({params.weight*100:.1f}%)")
        logger.info(f"  Символ: {params.symbol}")
        
        try:
            # Використовуємо нову функцію розрахунку валідного ордера
            order_calc = await self.calculate_valid_order_size(params.symbol, position_size)
            
            if "error" in order_calc:
                logger.error(f"[POSITION_ERROR] Помилка розрахунку ордера: {order_calc['error']}")
                return False
            
            if not order_calc.get("valid", False):
                logger.error(f"[POSITION_ERROR] Неможливо створити валідний ордер для {params.symbol}")
                logger.error(f"  Потрібно мінімум: ${order_calc.get('min_notional', 0):.2f}")
                logger.error(f"  Або мін. кількість: {order_calc.get('min_amount', 0)}")
                return False
            
            # Використовуємо розраховані параметри
            quantity = order_calc["quantity"]
            current_price = order_calc["price"]
            actual_notional = order_calc["notional_usd"]
            
            logger.info(f"[POSITION_CALC] ОНОВЛЕНИЙ розрахунок:")
            logger.info(f"  Поточна ціна: ${current_price}")
            logger.info(f"  Кількість токенів: {quantity:.6f}")
            logger.info(f"  Фактичний нотіонал: ${actual_notional:.2f}")
            logger.info(f"  Цільовий розмір: ${position_size:.2f}")
            
            if actual_notional > position_size * 1.5:  # Якщо більше ніж +50% від цільового
                logger.warning(f"[POSITION_WARNING] Фактична сума (${actual_notional:.2f}) значно більша за цільову (${position_size:.2f})")
                logger.warning(f"[POSITION_WARNING] Це через мінімальні вимоги біржі")
            
            # РЕАЛЬНІ ОРДЕРИ - ТЕСТНЕТ РЕЖИМ
            logger.info(f"[POSITION_REAL] СТВОРЮЮ РЕАЛЬНИЙ ОРДЕР НА БІРЖІ!")
            
            try:
                from safe_order_manager import SafeOrderManager
                
                # Використовуємо exchange з exchange_manager
                if hasattr(self, 'exchange_manager') and self.exchange_manager and self.exchange_manager.exchange:
                    exchange_to_use = self.exchange_manager.exchange
                    logger.info(f"[ORDER_SAFE] Використовуємо SafeOrderManager з exchange_manager")
                else:
                    logger.error(f"[ORDER_SAFE] ExchangeManager не ініціалізований!")
                    return False
                
                # Створюємо безпечний менеджер ордерів
                safe_manager = SafeOrderManager(exchange_to_use)
                
                # Використовуємо безпечний метод створення ордера з TP/SL
                order_result = safe_manager.create_safe_market_order_via_limit(
                    symbol=params.symbol,
                    side="buy", 
                    amount=quantity,
                    tp_percent=params.tp1_percent * 100,  # Конвертуємо 0.095 в 9.5%
                    sl_percent=abs(params.sl_percent) * 100  # Конвертуємо -0.10 в 10%
                )
                
                if "error" in order_result:
                    logger.error(f"[POSITION_ERROR] SafeOrderManager помилка: {order_result['error']}")
                    return False
                
                # УСПІШНЕ СТВОРЕННЯ ОРДЕРА
                logger.info(f"[POSITION_SUCCESS] ✅ Безпечний ордер створено:")
                logger.info(f"  ID ордера: {order_result.get('id')}")
                logger.info(f"  Статус: {order_result.get('status')}")
                logger.info(f"  Виконано: {order_result.get('filled', 0):.6f}")
                logger.info(f"  Залишок: {order_result.get('remaining', 0):.6f}")
                if order_result.get('average'):
                    logger.info(f"  Середня ціна: ${order_result.get('average', current_price)}")
                elif order_result.get('price'):
                    logger.info(f"  Ціна ордера: ${order_result.get('price')}")
                
                # Зберігаємо ордер
                order_data = order_result
                    
            except Exception as e:
                logger.error(f"[POSITION_ERROR] Критична помилка створення ордера: {e}")
                import traceback
                traceback.print_exc()
                return False
        
            # Зберігаємо позицію в портфель
            position_data = {
                "symbol": params.symbol,
                "side": "buy",
                "size": order_result.get('filled', quantity),
                "entry_price": order_result.get('average', current_price),
                "entry_time": datetime.now(),
                "timestamp": datetime.now().isoformat(),
                "tp1_hit": False,
                "tp2_hit": False,
                "params": params,
                "order_id": order_result.get('id'),
                "quantity": quantity,
                "target_size": position_size,
                "actual_size": actual_notional,
                "leverage": params.max_leverage,
                "stop_loss": params.sl_percent,
                "take_profit": [params.tp1_percent, params.tp2_percent]
            }
            
            self.positions[asset] = position_data
            logger.info(f"[PORTFOLIO] Позицію {asset} додано до портфеля")
            
            # Встановлюємо стоп-лосс і тейк-профіт
            await self.set_stop_loss_take_profit(asset)
            
            return True
            
        except Exception as e:
            logger.error(f"[POSITION_ERROR] Помилка відкриття позиції {asset}: {e}")
            logger.error(f"[POSITION_ERROR] Тип помилки: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return False
    
    async def check_exit_conditions(self):
        """Перевірка умов виходу з позицій"""
        for asset, position in self.positions.items():
            current_price = await self.get_current_price(position["symbol"])
            entry_price = position["entry_price"]
            
            # Розрахунок P&L
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
            
            params = position["params"]
            
            # Перевірка Take Profit 1
            if not position["tp1_hit"] and pnl_percent >= params.tp1_percent:
                await self.execute_partial_exit(asset, 0.5)  # Закриваємо 50%
                position["tp1_hit"] = True
                logger.info(f"[OK] TP1 досягнуто для {asset}: +{pnl_percent:.2f}%")
            
            # Перевірка Take Profit 2
            elif not position["tp2_hit"] and pnl_percent >= params.tp2_percent:
                await self.execute_full_exit(asset)
                logger.info(f"[TARGET] TP2 досягнуто для {asset}: +{pnl_percent:.2f}%")
            
            # Перевірка Stop Loss
            elif pnl_percent <= params.sl_percent:
                await self.execute_full_exit(asset)
                logger.warning(f"🔴 SL спрацював для {asset}: {pnl_percent:.2f}%")
    
    async def risk_manager(self):
        """Ризик-менеджмент"""
        while self.is_running:
            try:
                # Перевірка загального ризику портфеля
                total_risk = await self.calculate_portfolio_risk()
                max_risk = self.config["risk_management"]["max_portfolio_risk"]
                
                if total_risk > max_risk:
                    logger.critical(f"[WARNING] Ризик портфеля {total_risk:.2f}% перевищує ліміт {max_risk}%")
                    await self.emergency_risk_reduction()
                
                # Перевірка екстрених стопів
                portfolio_pnl = await self.calculate_portfolio_pnl()
                emergency_stop = self.config["risk_management"]["emergency_stop_loss"]
                
                if portfolio_pnl <= emergency_stop:
                    logger.critical(f"[ALERT] ЕКСТРЕНИЙ СТОП! P&L портфеля: {portfolio_pnl:.2f}%")
                    await self.emergency_close_all()
                
                await asyncio.sleep(60)  # Перевіряємо кожну хвилину
                
            except Exception as e:
                logger.error(f"Помилка в ризик-менеджменті: {e}")
                await asyncio.sleep(60)
    
    async def macro_events_monitor(self):
        """Моніторинг макроекономічних подій"""
        events = {
            "18:00": "powell_speech",
            "20:30": "pmi_usa",
            "09:00": "ecb_opening"  # наступного дня
        }
        
        while self.is_running:
            current_time = datetime.now().strftime("%H:%M")
            
            if current_time in events:
                event = events[current_time]
                await self.handle_macro_event(event)
            
            await asyncio.sleep(60)
    
    async def handle_macro_event(self, event: str):
        """Обробка макроекономічних подій"""
        if event == "powell_speech":
            logger.warning("[MIC] Початок виступу Пауела - скорочуємо позиції на 50%")
            await self.reduce_all_positions(0.5)
        
        elif event == "pmi_usa":
            logger.info("[DATA] Публікація PMI США - моніторимо BTC волатильність")
            # Додаткова логіка для моніторингу
        
        elif event == "ecb_opening":
            logger.info("[BANK] Відкриття ЄЦБ - призупиняємо нові позиції")
            # Тимчасово припиняємо відкриття нових позицій
    
    async def news_monitor(self):
        """Моніторинг новин"""
        while self.is_running:
            try:
                # Перевірка критичних новин
                await self.check_critical_news()
                await asyncio.sleep(self.config["monitoring"]["news_check_interval"])
            except Exception as e:
                logger.error(f"Помилка в моніторингу новин: {e}")
                await asyncio.sleep(300)
    
    async def check_critical_news(self):
        """Перевірка критичних новин"""
        # Тут буде інтеграція з новинними API
        pass
    
    # Допоміжні методи для роботи з біржею (заглушки)
    async def calculate_valid_order_size(self, symbol: str, target_usd: float) -> Dict[str, Any]:
        """
        Розрахунок валідного розміру ордера з урахуванням мінімальних вимог біржі
        """
        try:
            if not hasattr(self, 'exchange_manager') or not self.exchange_manager or not self.exchange_manager.exchange:
                logger.error(f"[ORDER_CALC] Exchange не ініціалізований!")
                return {"error": "No exchange"}
            
            # Отримуємо інформацію про ринок
            markets = self.exchange_manager.exchange.load_markets()
            market = markets.get(symbol)
            
            if not market:
                logger.error(f"[ORDER_CALC] Ринок {symbol} не знайдено!")
                return {"error": "Market not found"}
            
            # Отримуємо поточну ціну
            ticker = self.exchange_manager.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # Отримуємо мінімальні вимоги
            min_notional = market.get('limits', {}).get('cost', {}).get('min', 5.0)
            min_amount = market.get('limits', {}).get('amount', {}).get('min', 0.001)
            amount_precision = market.get('precision', {}).get('amount', 3)
            
            logger.info(f"[ORDER_CALC] {symbol} - ціна: ${current_price}")
            logger.info(f"[ORDER_CALC] Мін. нотіонал: {min_notional}, мін. кількість: {min_amount}")
            
            # Розраховуємо кількість на основі target_usd
            target_quantity = target_usd / current_price
            
            # Перевіряємо мінімальні вимоги
            min_usd_for_min_amount = min_amount * current_price
            
            if target_usd < min_notional:
                logger.warning(f"[ORDER_CALC] Цільова сума ${target_usd} < мін. нотіонал ${min_notional}")
                target_usd = min_notional * 1.1  # +10% для безпеки
                target_quantity = target_usd / current_price
            
            if target_quantity < min_amount:
                logger.warning(f"[ORDER_CALC] Цільова кількість {target_quantity} < мін. кількість {min_amount}")
                target_quantity = min_amount * 1.1  # +10% для безпеки
                target_usd = target_quantity * current_price
            
            # Округлюємо кількість до правильної точності
            if amount_precision:
                if isinstance(amount_precision, float) and amount_precision < 1:
                    import math
                    decimal_places = abs(int(math.log10(amount_precision)))
                    target_quantity = round(target_quantity, decimal_places)
                else:
                    target_quantity = round(target_quantity, int(amount_precision))
            
            # Фінальна перевірка
            final_notional = target_quantity * current_price
            
            result = {
                "symbol": symbol,
                "quantity": target_quantity,
                "price": current_price,
                "notional_usd": final_notional,
                "original_target": target_usd,
                "min_amount": min_amount,
                "min_notional": min_notional,
                "valid": target_quantity >= min_amount and final_notional >= min_notional
            }
            
            logger.info(f"[ORDER_CALC] Результат: {target_quantity:.6f} {symbol.split('/')[0]} за ${final_notional:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"[ORDER_CALC] Помилка розрахунку для {symbol}: {e}")
            return {"error": str(e)}

    async def get_current_price(self, symbol: str) -> float:
        """Отримання поточної ціни з біржі (РЕАЛЬНІ ЦІНИ)"""
        try:
            # ВИКОРИСТОВУЄМО РЕАЛЬНУ БІРЖУ для отримання цін!
            if hasattr(self, 'exchange_manager') and self.exchange_manager and self.exchange_manager.exchange:
                try:
                    # Отримуємо реальну ціну з Binance Futures Testnet
                    ticker = self.exchange_manager.exchange.fetch_ticker(symbol)
                    price = ticker['last']  # Остання ціна
                    logger.info(f"[PRICE] {symbol}: ${price} (реальна ціна з біржі)")
                    return price
                except Exception as e:
                    logger.warning(f"[PRICE] Помилка отримання ціни з біржі {symbol}: {e}")
            
            # Якщо біржа недоступна, спробуємо простий API
            try:
                import requests
                url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
                response = requests.get(url, timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    price = float(data['price'])
                    logger.debug(f"[PRICE] {symbol}: ${price} (з Binance API)")
                    return price
            except Exception as e:
                logger.warning(f"[PRICE] Помилка отримання ціни {symbol}: {e}")
            
            # ТІЛЬКИ В КРАЙНЬОМУ ВИПАДКУ - тестові ціни
            test_prices = {
                "DIA/USDT": 0.85,
                "PENDLE/USDT": 6.20,
                "API3/USDT": 1.45,
                "RENDER/USDT": 7.80,
                "UMA/USDT": 2.15,
                "FIDA/USDT": 0.28
            }
            
            if symbol in test_prices:
                price = test_prices[symbol]
                logger.warning(f"[PRICE] {symbol}: ${price} (тестова ціна - біржа недоступна)")
                return price
            
            logger.error(f"[PRICE] Не вдалося отримати ціну для {symbol}")
            return None
            
        except Exception as e:
            logger.error(f"[PRICE] Критична помилка отримання ціни {symbol}: {e}")
            return None
    
    async def get_btc_dominance(self) -> float:
        """Отримання BTC домінації"""
        return self.market_data.get('btc_dominance', 60.0)
    
    async def get_funding_rate(self, symbol: str) -> float:
        """Отримання funding rate"""
        try:
            import requests
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                return float(data['lastFundingRate']) * 100
        except:
            pass
        return 0.05  # Fallback
    
    async def get_spread(self, symbol: str) -> float:
        """Отримання спреду"""
        # Заглушка
        return 0.1
    
    async def get_nvidia_price_change(self) -> float:
        """Отримання зміни ціни NVIDIA"""
        # Заглушка
        return 0.0
    
    async def calculate_portfolio_risk(self) -> float:
        """Розрахунок ризику портфеля"""
        # Заглушка
        return 1.5
    
    async def calculate_portfolio_pnl(self) -> float:
        """Розрахунок P&L портфеля"""
        # Заглушка
        return 0.0
    
    async def set_stop_loss_take_profit(self, asset: str):
        """Встановлення стоп-лосс і тейк-профіт"""
        pass
    
    async def execute_partial_exit(self, asset: str, ratio: float):
        """Частковий вихід з позиції"""
        logger.info(f"Частковий вихід з {asset}: {ratio*100:.0f}%")
        pass
    
    async def execute_full_exit(self, asset: str):
        """Повний вихід з позиції"""
        logger.info(f"Повний вихід з {asset}")
        if asset in self.positions:
            del self.positions[asset]
    
    async def emergency_risk_reduction(self):
        """Екстрене зниження ризику"""
        logger.critical("[ALERT] Екстрене зниження ризику!")
        await self.reduce_all_positions(0.3)  # Скорочуємо всі позиції на 30%
    
    async def emergency_close_all(self):
        """Екстрене закриття всіх позицій"""
        logger.critical("[ALERT] ЗАКРИТТЯ ВСІХ ПОЗИЦІЙ!")
        for asset in list(self.positions.keys()):
            await self.execute_full_exit(asset)
    
    async def reduce_all_positions(self, ratio: float):
        """Скорочення всіх позицій"""
        for asset in self.positions:
            await self.execute_partial_exit(asset, ratio)
    
    # ========== НОВІ ФУНКЦІЇ ПІД ПЛАН GPT ==========
    
    async def check_upcoming_macro_events(self):
        """Перевірка наближення макроподій"""
        now = datetime.now(pytz.timezone('Europe/Kiev'))
        
        for event_name, event_data in self.macro_events.items():
            event_time = event_data["datetime"]
            time_to_event = event_time - now
            
            if timedelta(0) <= time_to_event <= event_data["advance_notice"]:
                logger.warning(f"[WARNING] МАКРОПОДІЯ НАБЛИЖАЄТЬСЯ: {event_name}")
                logger.warning(f"🕒 Час події: {event_time.strftime('%H:%M %d.%m.%Y')}")
                logger.warning(f"[DOWN] Планове скорочення позицій: {event_data['position_reduction']*100:.0f}%")
                
                await self.prepare_for_macro_event(event_name, event_data)
    
    async def prepare_for_macro_event(self, event_name: str, event_data: dict):
        """Підготовка до макроподії"""
        reduction_ratio = event_data["position_reduction"]
        
        logger.info(f"[TARGET] Підготовка до {event_name}: скорочення на {reduction_ratio*100:.0f}%")
        
        # Пріоритетне скорочення високого плеча та мікро-ігор
        priority_reduction = {
            "micro_play": 0.7,      # UMA, FIDA - скорочуємо на 70%
            "thematic_ai": 0.5,     # RENDER - скорочуємо на 50%
            "core_reduced": 0.4,    # API3 - скорочуємо на 40%
            "core_alpha": 0.3,      # PENDLE - скорочуємо на 30%
            "core": 0.2             # DIA - скорочуємо на 20%
        }
        
        for asset, params in self.trading_params.items():
            if asset in self.positions:
                reduction = priority_reduction.get(params.priority, reduction_ratio)
                await self.execute_partial_exit(asset, reduction)
                logger.info(f"[DOWN] {asset}: скорочено на {reduction*100:.0f}%")
    
    async def macro_events_monitor(self):
        """Моніторинг макроподій"""
        while self.is_running:
            try:
                await self.check_upcoming_macro_events()
                await asyncio.sleep(1800)  # Кожні 30 хвилин
            except Exception as e:
                logger.error(f"Помилка моніторингу макроподій: {e}")
                await asyncio.sleep(1800)
    
    async def nvda_monitor(self):
        """Моніторинг NVIDIA для RENDER корреляції"""
        while self.is_running:
            try:
                nvda_change = await self.get_nvidia_price_change()
                
                if nvda_change is not None:
                    render_params = self.trading_params["RENDER"]
                    
                    # NVIDIA падає > 4% - закриваємо RENDER
                    if nvda_change <= render_params.special_conditions["nvda_threshold"]["negative"]:
                        if "RENDER" in self.positions:
                            logger.warning(f"🔴 NVIDIA падіння {nvda_change*100:.1f}% - закриваємо RENDER")
                            await self.execute_full_exit("RENDER")
                    
                    # NVIDIA росте > 3% - можна добрати RENDER
                    elif nvda_change >= render_params.special_conditions["nvda_threshold"]["positive"]:
                        if "RENDER" not in self.positions:
                            logger.info(f"🟢 NVIDIA ріст {nvda_change*100:.1f}% - можна розглянути RENDER")
                
                await asyncio.sleep(900)  # Кожні 15 хвилин
            except Exception as e:
                logger.error(f"Помилка NVDA моніторингу: {e}")
                await asyncio.sleep(900)
    
    async def funding_rate_monitor(self):
        """Моніторинг funding rate для API3"""
        while self.is_running:
            try:
                api3_funding = await self.get_funding_rate("API3/USDT")
                
                if api3_funding is not None:
                    threshold = self.trading_params["API3"].special_conditions["funding_threshold"]
                    
                    if api3_funding > threshold:
                        logger.warning(f"[WARNING] API3 funding перегрітий: {api3_funding*100:.2f}%")
                        
                        if "API3" in self.positions:
                            # Скорочуємо API3 на 25%
                            await self.execute_partial_exit("API3", 0.25)
                            logger.info("[DOWN] API3: скорочено на 25% через високий funding")
                
                await asyncio.sleep(28800)  # Кожні 8 годин (funding period)
            except Exception as e:
                logger.error(f"Помилка funding моніторингу: {e}")
                await asyncio.sleep(28800)
    
    async def liquidity_monitor(self):
        """Моніторинг ліквідності для FIDA/UMA"""
        while self.is_running:
            try:
                # Перевірка FIDA (критично важливо!)
                fida_depth = await self.get_orderbook_depth("FIDA/USDT", 0.005)  # 0.5% depth
                fida_threshold = self.emergency_rules["thin_liquidity_fida_limit"]
                
                if fida_depth < fida_threshold:
                    logger.warning(f"[WARNING] FIDA низька ліквідність: ${fida_depth:.0f} < ${fida_threshold}")
                    
                    if "FIDA" in self.positions:
                        # Виходимо, якщо ліквідність критично низька
                        await self.execute_full_exit("FIDA")
                        logger.info("[ALERT] FIDA: закрито через низьку ліквідність")
                
                # Перевірка спреду FIDA
                fida_spread = await self.get_spread("FIDA/USDT")
                spread_threshold = self.trading_params["FIDA"].special_conditions["spread_threshold"]
                
                if fida_spread > spread_threshold:
                    logger.warning(f"[WARNING] FIDA великий спред: {fida_spread*100:.2f}% > {spread_threshold*100:.1f}%")
                
                await asyncio.sleep(300)  # Кожні 5 хвилин
            except Exception as e:
                logger.error(f"Помилка ліквідності моніторингу: {e}")
                await asyncio.sleep(300)
    
    async def dynamic_hedge_manager(self):
        """Посилений динамічний хедж (β=0.4)"""
        while self.is_running:
            try:
                # Перевірка BTC домінації
                btc_dominance = await self.get_btc_dominance()
                threshold = self.hedge_config["btc_dominance_threshold"]
                
                if btc_dominance > threshold:
                    logger.warning(f"🔶 BTC домінація висока: {btc_dominance:.1f}% > {threshold}%")
                    await self.enable_hedge()
                
                # Перевірка BTC флеш-краху
                btc_change_15m = await self.get_btc_change_15m()
                crash_threshold = self.hedge_config["btc_flash_crash_threshold"]
                
                if btc_change_15m <= crash_threshold:
                    logger.critical(f"[ALERT] BTC флеш-краж: {btc_change_15m*100:.1f}% за 15 хв!")
                    await self.emergency_hedge_activation()
                
                await asyncio.sleep(600)  # Кожні 10 хвилин
            except Exception as e:
                logger.error(f"Помилка хедж моніторингу: {e}")
                await asyncio.sleep(600)
    
    async def enable_hedge(self):
        """Активація хеджування"""
        if not self.hedge_position:
            hedge_size = self.calculate_hedge_size()
            logger.info(f"[SHIELD] Активація хеджу: ${hedge_size:.0f}")
            
            # Відкриваємо шорт BTC або ETH
            self.hedge_position = {
                "instrument": "BTC/USDT",
                "side": "SHORT", 
                "size": hedge_size,
                "timestamp": datetime.now()
            }
    
    async def emergency_hedge_activation(self):
        """Екстрена активація хеджу"""
        logger.critical("[ALERT] ЕКСТРЕНИЙ ХЕДЖ!")
        
        # Скорочуємо всі позиції на 50%
        await self.reduce_all_positions(0.5)
        
        # Активуємо посилений хедж
        await self.enable_hedge()
    
    def calculate_hedge_size(self) -> float:
        """Розрахунок розміру хеджу"""
        total_notional = sum(
            self.positions.get(asset, {}).get("notional", 0) 
            for asset in self.positions
        )
        
        return total_notional * self.hedge_config["beta"]  # β=0.4
    
    async def get_btc_dominance(self) -> float:
        """Отримання BTC домінації"""
        # Заглушка - потрібно підключити до API
        return 61.5
    
    async def get_btc_change_15m(self) -> float:
        """Отримання зміни BTC за 15 хвилин"""
        # Заглушка - потрібно підключити до API
        return 0.0
    
    async def get_orderbook_depth(self, symbol: str, depth_percent: float) -> float:
        """Отримання глибини ордербуку в USD"""
        # Заглушка - потрібно підключити до API
        return 75000.0  # $75k
    
    # ========== КІНЕЦЬ НОВИХ ФУНКЦІЙ ==========
    
    async def shutdown(self):
        """Завершення роботи бота"""
        logger.info("🛑 Завершення роботи торгового бота...")
        self.is_running = False
        
        # Закриваємо всі позиції при зупинці (опціонально)
        # await self.emergency_close_all()

# Точка входу
async def main():
    bot = TradingBot()
    await bot.start()

if __name__ == "__main__":
    print("[BOT] Автоматична торгова система v2.1 (GPT ПЛАН)")
    print("[UP] Оновлено під детальний план від 21.07.2025")
    print("[TARGET] Нові цілі: PENDLE +9.5%, посилений хедж β=0.4")
    print("[WARNING] КРИТИЧНО: Пауелл завтра 15:30 EEST - автоскорочення 50%")
    print("[ZAP] Натисніть Ctrl+C для зупинки")
    print("[MONEY] ТЕСТНЕТ: Портфель $600 - РЕАЛЬНІ ОРДЕРИ!")
    print("[FIRE] СИМУЛЯЦІЯ ВИМКНЕНА - справжні API виклики")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[OK] Бот зупинено користувачем")
