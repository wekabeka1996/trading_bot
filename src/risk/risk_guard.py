"""
[SHIELD] RISK GUARD - Справжній ризик-менеджмент
НЕ просто %-ки, а МАТЕМАТИЧНИЙ VaR розрахунок!
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
import json

logger = logging.getLogger(__name__)

class RiskGuard:
    """Справжній ризик-менеджмент з математичним VaR"""
    
    def __init__(self, exchange, max_portfolio_var=0.025):
        self.exchange = exchange
        self.max_portfolio_var = max_portfolio_var  # 2.5%
        self.max_position_risk = 0.005  # 0.5% на позицію
        self.historical_data = {}  # {symbol: price_data}
        self.correlation_matrix = None
        self.volatilities = {}
        self.last_update = None
        
    async def initialize_risk_models(self, symbols: List[str], days=60):
        """Ініціалізація ризик-моделей з історичними даними"""
        try:
            logger.info("[DATA] Завантаження історичних даних для ризик-моделі...")
            
            # Завантажуємо історичні дані
            for symbol in symbols:
                try:
                    # Отримуємо дані за останні 60 днів
                    since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
                    
                    ohlcv = await self.exchange.fetch_ohlcv(
                        symbol, '1d', since=since, limit=days
                    )
                    
                    if len(ohlcv) >= 30:  # Мінімум 30 днів
                        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        df['returns'] = df['close'].pct_change().dropna()
                        
                        self.historical_data[symbol] = df
                        logger.info(f"[OK] Завантажено {len(df)} днів для {symbol}")
                    else:
                        logger.warning(f"[WARNING] Недостатньо даних для {symbol}: {len(ohlcv)} днів")
                        
                except Exception as e:
                    logger.error(f"[ERROR] Помилка завантаження даних {symbol}: {e}")
            
            # Розраховуємо кореляційну матрицю
            await self.calculate_correlation_matrix()
            
            # Розраховуємо волатильності
            await self.calculate_volatilities()
            
            self.last_update = datetime.now()
            logger.info(f"[SHIELD] Ризик-модель ініціалізована для {len(self.historical_data)} активів")
            
        except Exception as e:
            logger.error(f"[ERROR] Критична помилка ініціалізації ризик-моделі: {e}")
    
    async def calculate_correlation_matrix(self):
        """Розрахунок кореляційної матриці між активами"""
        try:
            if len(self.historical_data) < 2:
                logger.warning("[WARNING] Недостатньо активів для кореляційної матриці")
                return
            
            # Створюємо DataFrame з доходностями всіх активів
            returns_data = {}
            min_length = min(len(data) for data in self.historical_data.values())
            
            for symbol, data in self.historical_data.items():
                # Беремо останні min_length записів для синхронізації
                returns_data[symbol] = data['returns'].tail(min_length).values
            
            returns_df = pd.DataFrame(returns_data)
            
            # Розраховуємо кореляційну матрицю
            self.correlation_matrix = returns_df.corr()
            
            logger.info("[DATA] Кореляційна матриця розрахована")
            logger.info(f"Середня кореляція: {self.correlation_matrix.values[np.triu_indices_from(self.correlation_matrix.values, k=1)].mean():.3f}")
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка розрахунку кореляційної матриці: {e}")
    
    async def calculate_volatilities(self):
        """Розрахунок волатільностей активів"""
        try:
            for symbol, data in self.historical_data.items():
                returns = data['returns'].dropna()
                
                if len(returns) >= 20:
                    # Річна волатільність (252 торгівельні дні)
                    daily_vol = returns.std()
                    annual_vol = daily_vol * np.sqrt(252)
                    
                    # EWMA волатільність (експоненційно-зважена)
                    ewma_vol = returns.ewm(span=20).std().iloc[-1] * np.sqrt(252)
                    
                    self.volatilities[symbol] = {
                        'daily': daily_vol,
                        'annual': annual_vol,
                        'ewma_annual': ewma_vol,
                        'last_update': datetime.now()
                    }
                    
                    logger.info(f"[UP] {symbol}: волатільність {annual_vol:.1%} (EWMA: {ewma_vol:.1%})")
        
        except Exception as e:
            logger.error(f"[ERROR] Помилка розрахунку волатільностей: {e}")
    
    def calculate_position_var(self, symbol: str, position_size_usd: float, confidence=0.05) -> float:
        """
        Розрахунок VaR для окремої позиції
        confidence=0.05 означає 95% VaR (5% ймовірність втрат більших за VaR)
        """
        try:
            if symbol not in self.volatilities:
                logger.warning(f"[WARNING] Немає даних волатільності для {symbol}")
                return position_size_usd * 0.05  # Консервативна оцінка 5%
            
            # Отримуємо денну волатільність
            daily_vol = self.volatilities[symbol]['daily']
            
            # Z-score для заданого рівня довіри
            z_score = norm.ppf(confidence)  # Для 95% VaR = -1.645
            
            # VaR = Position_Size * |Z-score| * Daily_Volatility
            var = position_size_usd * abs(z_score) * daily_vol
            
            return var
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка розрахунку позиційного VaR для {symbol}: {e}")
            return position_size_usd * 0.05
    
    def calculate_portfolio_var(self, positions: Dict[str, float], confidence=0.05) -> Tuple[float, dict]:
        """
        Розрахунок портфельного VaR з урахуванням кореляцій
        positions = {symbol: position_size_usd}
        """
        try:
            if self.correlation_matrix is None:
                logger.warning("[WARNING] Кореляційна матриця не розрахована, використовуємо прості суми")
                total_var = sum(
                    self.calculate_position_var(symbol, size, confidence) 
                    for symbol, size in positions.items()
                )
                return total_var, {'method': 'simple_sum', 'diversification_benefit': 0}
            
            # Створюємо вектор позицій
            symbols = list(positions.keys())
            position_values = [positions[symbol] for symbol in symbols]
            
            # Вектор VaR для кожної позиції
            individual_vars = [
                self.calculate_position_var(symbol, positions[symbol], confidence) 
                for symbol in symbols
            ]
            
            # Створюємо матрицю коваріацій VaR
            n = len(symbols)
            covariance_matrix = np.zeros((n, n))
            
            for i in range(n):
                for j in range(n):
                    if i == j:
                        covariance_matrix[i, j] = individual_vars[i] ** 2
                    else:
                        # Коваріація = VaR_i * VaR_j * Correlation_ij
                        symbol_i, symbol_j = symbols[i], symbols[j]
                        if symbol_i in self.correlation_matrix.index and symbol_j in self.correlation_matrix.columns:
                            correlation = self.correlation_matrix.loc[symbol_i, symbol_j]
                            covariance_matrix[i, j] = individual_vars[i] * individual_vars[j] * correlation
                        else:
                            covariance_matrix[i, j] = 0
            
            # Портфельний VaR = sqrt(w' * Σ * w), де w - ваги (в нашому випадку = 1)
            weights = np.ones(n)  # Рівні ваги
            portfolio_var = np.sqrt(weights @ covariance_matrix @ weights.T)
            
            # Вигода від диверсифікації
            simple_sum_var = sum(individual_vars)
            diversification_benefit = (simple_sum_var - portfolio_var) / simple_sum_var
            
            return portfolio_var, {
                'method': 'correlation_adjusted',
                'individual_vars': dict(zip(symbols, individual_vars)),
                'simple_sum': simple_sum_var,
                'diversification_benefit': diversification_benefit,
                'correlation_matrix_size': covariance_matrix.shape
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка розрахунку портфельного VaR: {e}")
            # Fallback до простої суми
            total_var = sum(
                self.calculate_position_var(symbol, size, confidence) 
                for symbol, size in positions.items()
            )
            return total_var, {'method': 'fallback', 'error': str(e)}
    
    async def validate_position_risk(self, symbol: str, position_size_usd: float, 
                                   current_positions: Dict[str, float]) -> Tuple[bool, dict]:
        """Валідація ризику нової позиції"""
        try:
            # 1. Перевіряємо ризик окремої позиції
            position_var = self.calculate_position_var(symbol, position_size_usd)
            position_risk_pct = position_var / position_size_usd
            
            # 2. Розраховуємо новий портфельний ризик
            new_positions = current_positions.copy()
            new_positions[symbol] = new_positions.get(symbol, 0) + position_size_usd
            
            portfolio_var, portfolio_details = self.calculate_portfolio_var(new_positions)
            total_portfolio_value = sum(new_positions.values())
            portfolio_risk_pct = portfolio_var / total_portfolio_value if total_portfolio_value > 0 else 0
            
            # 3. Перевіряємо ліміти
            position_ok = position_risk_pct <= self.max_position_risk
            portfolio_ok = portfolio_risk_pct <= self.max_portfolio_var
            
            risk_details = {
                'position_var_usd': position_var,
                'position_risk_pct': position_risk_pct,
                'position_limit_pct': self.max_position_risk,
                'position_approved': position_ok,
                'portfolio_var_usd': portfolio_var,
                'portfolio_risk_pct': portfolio_risk_pct,
                'portfolio_limit_pct': self.max_portfolio_var,
                'portfolio_approved': portfolio_ok,
                'portfolio_details': portfolio_details,
                'recommendation': 'APPROVE' if (position_ok and portfolio_ok) else 'REJECT'
            }
            
            if not position_ok:
                logger.warning(f"[WARNING] Позиційний ризик перевищено: {position_risk_pct:.2%} > {self.max_position_risk:.2%}")
            
            if not portfolio_ok:
                logger.warning(f"[WARNING] Портфельний ризик перевищено: {portfolio_risk_pct:.2%} > {self.max_portfolio_var:.2%}")
            
            return (position_ok and portfolio_ok), risk_details
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка валідації ризику: {e}")
            return False, {'error': str(e), 'recommendation': 'REJECT'}
    
    def get_optimal_position_size(self, symbol: str, available_capital: float, 
                                 target_risk_pct: float = 0.003) -> float:
        """
        Розрахунок оптимального розміру позиції для заданого рівня ризику
        target_risk_pct = 0.3% (наш таргет на позицію)
        """
        try:
            if symbol not in self.volatilities:
                logger.warning(f"[WARNING] Немає даних волатільності для {symbol}")
                return available_capital * 0.1  # Консервативно 10%
            
            daily_vol = self.volatilities[symbol]['daily']
            z_score = abs(norm.ppf(0.05))  # 95% VaR
            
            # Target_Risk = Position_Size * Z-score * Daily_Vol
            # Position_Size = Target_Risk / (Z-score * Daily_Vol)
            optimal_size = (available_capital * target_risk_pct) / (z_score * daily_vol)
            
            # Обмежуємо максимальним розміром
            max_size = available_capital * 0.2  # Максимум 20% капіталу
            optimal_size = min(optimal_size, max_size)
            
            logger.info(f"[MONEY] Оптимальний розмір для {symbol}: ${optimal_size:,.0f} (ризик {target_risk_pct:.1%})")
            
            return optimal_size
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка розрахунку оптимального розміру для {symbol}: {e}")
            return available_capital * 0.1
    
    async def update_risk_models(self):
        """Оновлення ризик-моделей (раз на день)"""
        try:
            if self.last_update and (datetime.now() - self.last_update).days < 1:
                return  # Оновлюємо раз на день
            
            symbols = list(self.historical_data.keys())
            if symbols:
                await self.initialize_risk_models(symbols, days=60)
                logger.info("[REFRESH] Ризик-модель оновлена")
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка оновлення ризик-моделі: {e}")
    
    def generate_risk_report(self, current_positions: Dict[str, float]) -> dict:
        """Генерація ризик-звіту"""
        try:
            if not current_positions:
                return {'status': 'no_positions', 'message': 'Немає активних позицій'}
            
            portfolio_var, details = self.calculate_portfolio_var(current_positions)
            total_value = sum(current_positions.values())
            
            individual_risks = {}
            for symbol, size in current_positions.items():
                var = self.calculate_position_var(symbol, size)
                individual_risks[symbol] = {
                    'position_size_usd': size,
                    'var_usd': var,
                    'risk_pct': var / size if size > 0 else 0,
                    'weight_in_portfolio': size / total_value if total_value > 0 else 0
                }
            
            report = {
                'timestamp': datetime.now().isoformat(),
                'portfolio_summary': {
                    'total_value_usd': total_value,
                    'total_var_usd': portfolio_var,
                    'portfolio_risk_pct': portfolio_var / total_value if total_value > 0 else 0,
                    'risk_limit_pct': self.max_portfolio_var,
                    'risk_utilization': (portfolio_var / total_value) / self.max_portfolio_var if total_value > 0 else 0,
                    'status': 'OK' if portfolio_var / total_value <= self.max_portfolio_var else 'OVER_LIMIT'
                },
                'positions': individual_risks,
                'diversification': details,
                'risk_metrics': {
                    'correlation_matrix_available': self.correlation_matrix is not None,
                    'volatility_models_count': len(self.volatilities),
                    'last_model_update': self.last_update.isoformat() if self.last_update else None
                }
            }
            
            return report
            
        except Exception as e:
            logger.error(f"[ERROR] Помилка генерації ризик-звіту: {e}")
            return {'status': 'error', 'message': str(e)}

# Тест Risk Guard
async def test_risk_guard():
    """Тест без реального exchange"""
    
    class MockExchange:
        async def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
            # Симулюємо історичні дані з випадковими цінами
            np.random.seed(42)  # Для відтворюваності
            
            base_price = 50000 if 'BTC' in symbol else 100
            returns = np.random.normal(0, 0.02, 60)  # 60 днів, 2% волатільність
            
            prices = [base_price]
            for ret in returns:
                prices.append(prices[-1] * (1 + ret))
            
            ohlcv = []
            for i, price in enumerate(prices):
                ohlcv.append([
                    int((datetime.now() - timedelta(days=60-i)).timestamp() * 1000),
                    price * 0.99,  # open
                    price * 1.01,  # high
                    price * 0.98,  # low
                    price,         # close
                    1000000        # volume
                ])
            
            return ohlcv
    
    exchange = MockExchange()
    risk_guard = RiskGuard(exchange, max_portfolio_var=0.025)
    
    # Ініціалізуємо ризик-модель
    test_symbols = ['BTCUSDT', 'ETHUSDT', 'ADAUSDT']
    await risk_guard.initialize_risk_models(test_symbols)
    
    # Тестуємо валідацію позиції
    current_positions = {'BTCUSDT': 10000, 'ETHUSDT': 5000}  # $15k портфель
    
    is_valid, risk_details = await risk_guard.validate_position_risk(
        'ADAUSDT', 3000, current_positions
    )
    
    print(f"Позиція валідна: {is_valid}")
    print(f"Портфельний ризик: {risk_details['portfolio_risk_pct']:.2%}")
    
    # Генеруємо ризик-звіт
    new_positions = current_positions.copy()
    new_positions['ADAUSDT'] = 3000
    
    report = risk_guard.generate_risk_report(new_positions)
    print(f"Статус портфеля: {report['portfolio_summary']['status']}")

if __name__ == "__main__":
    asyncio.run(test_risk_guard())
