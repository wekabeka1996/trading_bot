# Безпечний менеджер ордерів для Binance Futures
# Версія: 1.0 - враховує PERCENT_PRICE фільтри та ліквідність

import logging
import time
from typing import Dict, Any, Optional
import ccxt

logger = logging.getLogger(__name__)

class SafeOrderManager:
    def __init__(self, exchange):
        self.exchange = exchange
        self.markets = {}
        self.tickers = {}
        
    def load_market_info(self, symbol: str) -> bool:
        """Завантаження інформації про ринок"""
        try:
            if not self.markets:
                self.markets = self.exchange.load_markets()
            
            if symbol not in self.markets:
                logger.error(f"[SAFE_ORDER] Символ {symbol} не знайдено на біржі")
                return False
                
            # Отримуємо свіжий тікер
            self.tickers[symbol] = self.exchange.fetch_ticker(symbol)
            logger.info(f"[SAFE_ORDER] {symbol} тікер оновлено")
            return True
            
        except Exception as e:
            logger.error(f"[SAFE_ORDER] Помилка завантаження ринку {symbol}: {e}")
            return False
    
    def get_safe_price(self, symbol: str, side: str = "buy") -> Optional[float]:
        """Отримання безпечної ціни з урахуванням PERCENT_PRICE фільтрів"""
        try:
            if symbol not in self.tickers:
                if not self.load_market_info(symbol):
                    return None
            
            ticker = self.tickers[symbol]
            market = self.markets[symbol]
            
            # Основні ціни
            last_price = ticker['last']
            bid_price = ticker.get('bid') or last_price * 0.999  # Fallback якщо bid=None
            ask_price = ticker.get('ask') or last_price * 1.001  # Fallback якщо ask=None
            
            logger.info(f"[SAFE_ORDER] {symbol} ціни:")
            logger.info(f"  Last: ${last_price}")
            logger.info(f"  Bid: ${bid_price} {'(fallback)' if not ticker.get('bid') else ''}")
            logger.info(f"  Ask: ${ask_price} {'(fallback)' if not ticker.get('ask') else ''}")
            
            # Перевіряємо PERCENT_PRICE фільтри
            filters = market.get('info', {}).get('filters', [])
            percent_price_filter = None
            
            for filter_item in filters:
                if filter_item.get('filterType') == 'PERCENT_PRICE':
                    percent_price_filter = filter_item
                    break
            
            if percent_price_filter:
                multiplier_up = float(percent_price_filter.get('multiplierUp', 1.1))
                multiplier_down = float(percent_price_filter.get('multiplierDown', 0.9))
                avg_price_mins = int(percent_price_filter.get('avgPriceMins', 5))
                
                logger.info(f"[SAFE_ORDER] PERCENT_PRICE фільтр:")
                logger.info(f"  Multiplier Up: {multiplier_up}")
                logger.info(f"  Multiplier Down: {multiplier_down}")
                logger.info(f"  Avg Price Mins: {avg_price_mins}")
                
                # Розраховуємо безпечні межі (консервативно)
                max_price = last_price * multiplier_up * 0.98  # 98% від максимуму
                min_price = last_price * multiplier_down * 1.02  # 102% від мінімуму
                
                if side == "buy":
                    # Для покупки: між last та max, але не вище ask + 0.1%
                    safe_price = min(ask_price * 1.001, max_price, last_price * 1.002)
                else:
                    # Для продажу: між min та last, але не нижче bid - 0.1%
                    safe_price = max(bid_price * 0.999, min_price, last_price * 0.998)
            else:
                # Якщо немає PERCENT_PRICE фільтра - консервативний підхід
                if side == "buy":
                    safe_price = min(ask_price * 1.001, last_price * 1.002)
                else:
                    safe_price = max(bid_price * 0.999, last_price * 0.998)
            
            logger.info(f"[SAFE_ORDER] Безпечна ціна для {side}: ${safe_price}")
            return safe_price
            
        except Exception as e:
            logger.error(f"[SAFE_ORDER] Помилка розрахунку безпечної ціни {symbol}: {e}")
            return None
    
    def check_liquidity(self, symbol: str, notional_usd: float) -> Dict[str, Any]:
        """Перевірка ліквідності для ордера"""
        try:
            if symbol not in self.tickers:
                if not self.load_market_info(symbol):
                    return {"valid": False, "reason": "No market data"}
            
            ticker = self.tickers[symbol]
            
            # Перевіряємо об'єм торгів за 24 години з fallback для None
            quote_volume_24h = ticker.get('quoteVolume') or 0
            base_volume_24h = ticker.get('baseVolume') or 0
            
            # Додаткова перевірка типу
            if not isinstance(quote_volume_24h, (int, float)):
                quote_volume_24h = 0
            if not isinstance(base_volume_24h, (int, float)):
                base_volume_24h = 0
            
            logger.info(f"[SAFE_ORDER] {symbol} ліквідність:")
            logger.info(f"  Quote Volume 24h: ${quote_volume_24h:,.0f}")
            logger.info(f"  Base Volume 24h: {base_volume_24h:,.0f}")
            logger.info(f"  Потрібний нотіонал: ${notional_usd:.2f}")
            
            # Мінімальні вимоги ліквідності для ТЕСТНЕТА (дуже знижені)
            min_quote_volume = {
                "BTC/USDT": 10000,      # $10K (було $100K)  
                "ETH/USDT": 5000,       # $5K (було $50K)
                "default": 50           # $50 (було $1K) - для альткоїнів на тестнеті
            }
            
            required_volume = min_quote_volume.get(symbol, min_quote_volume["default"])
            
            if quote_volume_24h < required_volume:
                return {
                    "valid": False, 
                    "reason": f"Low liquidity: ${quote_volume_24h:,.0f} < ${required_volume:,.0f}",
                    "volume_24h": quote_volume_24h
                }
            
            # Перевіряємо чи наш ордер не надто великий відносно НАШОГО балансу
            # Припустимо максимум 10% від балансу на один ордер для безпеки
            max_order_percent_of_balance = 0.10  # 10%
            estimated_balance = 14614.0  # USDT (можна отримати з exchange)
            max_order_size_by_balance = estimated_balance * max_order_percent_of_balance
            
            if notional_usd > max_order_size_by_balance:
                return {
                    "valid": False,
                    "reason": f"Order too large for balance: ${notional_usd:.2f} > ${max_order_size_by_balance:.2f} (10% of balance)",
                    "max_size": max_order_size_by_balance
                }
            
            # Додатково перевіряємо ліквідність ринку (але менш строго)
            if quote_volume_24h > 0:  
                market_order_size_limit = quote_volume_24h * 0.05  # 5% від ринку (було 1%)
                if notional_usd > market_order_size_limit:
                    logger.warning(f"[SAFE_ORDER] Великий ордер відносно ринку: ${notional_usd:.2f} > ${market_order_size_limit:.2f}")
                    # Але не відхиляємо, просто попереджуємо
                
                order_percent = (notional_usd / quote_volume_24h) * 100
            else:
                order_percent = 0
            
            return {
                "valid": True,
                "volume_24h": quote_volume_24h,
                "order_percent": order_percent
            }
            
        except Exception as e:
            logger.error(f"[SAFE_ORDER] Помилка перевірки ліквідності {symbol}: {e}")
            return {"valid": False, "reason": str(e)}
    
    def create_safe_limit_order(self, symbol: str, side: str, amount: float, max_slippage: float = 0.005) -> Dict[str, Any]:
        """Створення безпечного лімітного ордера"""
        try:
            logger.info(f"[SAFE_ORDER] Створення безпечного лімітного ордера:")
            logger.info(f"  Symbol: {symbol}")
            logger.info(f"  Side: {side}")
            logger.info(f"  Amount: {amount}")
            logger.info(f"  Max Slippage: {max_slippage * 100:.2f}%")
            
            # Завантажуємо інформацію про ринок
            if not self.load_market_info(symbol):
                return {"error": "Failed to load market info"}
            
            # Отримуємо безпечну ціну
            safe_price = self.get_safe_price(symbol, side)
            if not safe_price:
                return {"error": "Failed to get safe price"}
            
            # Перевіряємо ліквідність
            notional_usd = amount * safe_price
            liquidity_check = self.check_liquidity(symbol, notional_usd)
            
            if not liquidity_check["valid"]:
                return {"error": f"Liquidity issue: {liquidity_check['reason']}"}
            
            # Округлюємо кількість до правильної точності
            market = self.markets[symbol]
            amount_precision = market.get('precision', {}).get('amount', 6)
            
            if isinstance(amount_precision, float) and amount_precision < 1:
                import math
                decimal_places = abs(int(math.log10(amount_precision)))
                rounded_amount = round(amount, decimal_places)
            else:
                rounded_amount = round(amount, int(amount_precision))
            
            # Округлюємо ціну до правильної точності
            price_precision = market.get('precision', {}).get('price', 6)
            
            if isinstance(price_precision, float) and price_precision < 1:
                import math
                decimal_places = abs(int(math.log10(price_precision)))
                rounded_price = round(safe_price, decimal_places)
            else:
                rounded_price = round(safe_price, int(price_precision))
            
            logger.info(f"[SAFE_ORDER] Фінальні параметри:")
            logger.info(f"  Amount: {rounded_amount}")
            logger.info(f"  Price: ${rounded_price}")
            logger.info(f"  Notional: ${rounded_amount * rounded_price:.2f}")
            
            # Створюємо лімітний ордер
            order = self.exchange.create_order(
                symbol=symbol,
                type='limit',
                side=side,
                amount=rounded_amount,
                price=rounded_price
            )
            
            logger.info(f"[SAFE_ORDER] ✅ Лімітний ордер створено:")
            logger.info(f"  ID: {order.get('id')}")
            logger.info(f"  Status: {order.get('status')}")
            logger.info(f"  Price: ${order.get('price')}")
            logger.info(f"  Amount: {order.get('amount')}")
            
            return order
            
        except Exception as e:
            logger.error(f"[SAFE_ORDER] Помилка створення ордера: {e}")
            return {"error": str(e)}
    
    def create_safe_market_order_via_limit(self, symbol: str, side: str, amount: float, 
                                          tp_percent: float = None, sl_percent: float = None) -> Dict[str, Any]:
        """Безпечний ринковий ордер через лімітний з автоматичними TP/SL"""
        try:
            logger.info(f"[SAFE_ORDER] Створення безпечного 'ринкового' ордера через ліміт:")
            logger.info(f"  Symbol: {symbol}")
            logger.info(f"  Side: {side}")  
            logger.info(f"  Amount: {amount} (type: {type(amount)})")
            if tp_percent:
                logger.info(f"  Take Profit: +{tp_percent:.1f}%")
            if sl_percent:
                logger.info(f"  Stop Loss: -{sl_percent:.1f}%")
            
            # Перевіряємо що amount є числом
            if not isinstance(amount, (int, float)) or amount is None or amount <= 0:
                logger.error(f"[SAFE_ORDER] Invalid amount: {amount}")
                return {"error": f"Invalid amount: {amount}"}
            
            # Завантажуємо інформацію
            if not self.load_market_info(symbol):
                return {"error": "Failed to load market info"}
            
            ticker = self.tickers[symbol]
            
            # Отримуємо базову ціну та fallback значення
            last_price = ticker['last']
            if not isinstance(last_price, (int, float)) or last_price is None:
                logger.error(f"[SAFE_ORDER] Invalid last_price: {last_price} (type: {type(last_price)})")
                return {"error": "Invalid last price"}
                
            bid_price = ticker.get('bid') or last_price * 0.999  
            ask_price = ticker.get('ask') or last_price * 1.001
            
            # Додаткові перевірки типів
            if not isinstance(bid_price, (int, float)):
                bid_price = last_price * 0.999
            if not isinstance(ask_price, (int, float)):
                ask_price = last_price * 1.001
            
            logger.info(f"[SAFE_ORDER] Ціни для ордера:")
            logger.info(f"  Last: ${last_price}")
            logger.info(f"  Bid: ${bid_price} {'(fallback)' if not ticker.get('bid') else ''}")
            logger.info(f"  Ask: ${ask_price} {'(fallback)' if not ticker.get('ask') else ''}")
            
            # Для "ринкового" ордера використовуємо ціну з невеликим зсувом
            if side == "buy":
                # Купуємо по ask + 0.1%
                target_price = ask_price * 1.001
            else:
                # Продаємо по bid - 0.1%
                target_price = bid_price * 0.999
            
            logger.info(f"[SAFE_ORDER] Target price: ${target_price}")
            
            # Перевіряємо ліквідність
            logger.info(f"[SAFE_ORDER] Розраховуємо нотіонал: {amount} * {target_price}")
            notional_usd = amount * target_price
            logger.info(f"[SAFE_ORDER] Нотіонал: ${notional_usd:.2f}")
            
            liquidity_check = self.check_liquidity(symbol, notional_usd)
            
            if not liquidity_check["valid"]:
                return {"error": f"Liquidity issue: {liquidity_check['reason']}"}
            
            # Округлюємо параметри
            market = self.markets[symbol]
            
            # Кількість
            amount_precision = market.get('precision', {}).get('amount', 6)
            if isinstance(amount_precision, float) and amount_precision < 1:
                import math
                decimal_places = abs(int(math.log10(amount_precision)))
                rounded_amount = round(amount, decimal_places)
            else:
                rounded_amount = round(amount, int(amount_precision))
            
            # Ціна
            price_precision = market.get('precision', {}).get('price', 6)
            if isinstance(price_precision, float) and price_precision < 1:
                import math
                decimal_places = abs(int(math.log10(price_precision)))
                rounded_price = round(target_price, decimal_places)
            else:
                rounded_price = round(target_price, int(price_precision))
            
            logger.info(f"[SAFE_ORDER] Створюємо ліміт ордер як 'ринковий':")
            logger.info(f"  Amount: {rounded_amount}")
            logger.info(f"  Price: ${rounded_price}")
            
            # Підготовка параметрів ордера
            order_params = {}
            
            # Додаємо TP/SL якщо вказані
            if tp_percent and side == "buy":
                tp_price = rounded_price * (1 + tp_percent / 100)
                tp_price = round(tp_price, int(price_precision) if isinstance(price_precision, int) else abs(int(math.log10(price_precision))))
                order_params['takeProfit'] = {
                    'triggerPrice': tp_price,
                    'type': 'limit',
                    'price': tp_price
                }
                logger.info(f"[SAFE_ORDER] Take Profit: ${tp_price} (+{tp_percent:.1f}%)")
            
            if sl_percent and side == "buy":
                sl_price = rounded_price * (1 - sl_percent / 100)
                sl_price = round(sl_price, int(price_precision) if isinstance(price_precision, int) else abs(int(math.log10(price_precision))))
                order_params['stopLoss'] = {
                    'triggerPrice': sl_price,
                    'type': 'market'
                }
                logger.info(f"[SAFE_ORDER] Stop Loss: ${sl_price} (-{sl_percent:.1f}%)")
            
            # Створюємо лімітний ордер який має швидко виконатися
            order = self.exchange.create_order(
                symbol=symbol,
                type='limit',
                side=side,
                amount=rounded_amount,
                price=rounded_price,
                params=order_params
            )
            
            logger.info(f"[SAFE_ORDER] ✅ 'Ринковий' ордер створено:")
            logger.info(f"  ID: {order.get('id')}")
            logger.info(f"  Status: {order.get('status')}")
            if order_params:
                logger.info(f"  З автоматичними TP/SL: {list(order_params.keys())}")
            
            return order
            
        except Exception as e:
            logger.error(f"[SAFE_ORDER] Помилка створення ордера: {e}")
            return {"error": str(e)}