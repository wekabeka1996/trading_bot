# Модуль для ризик-менеджменту
import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class RiskMetrics:
    """Метрики ризику"""
    portfolio_var: float  # Value at Risk
    max_drawdown: float   # Максимальна просадка
    sharpe_ratio: float   # Коефіцієнт Шарпа
    total_exposure: float # Загальна експозиція
    correlation_risk: float # Ризик кореляції

@dataclass
class PositionRisk:
    """Ризик позиції"""
    symbol: str
    size: float
    risk_percent: float
    leverage: float
    stop_loss_distance: float
    max_loss_usd: float

class RiskManager:
    def __init__(self, portfolio_size: float, max_portfolio_risk: float = 2.5):
        """
        Ініціалізація ризик-менеджера
        
        Args:
            portfolio_size: Розмір портфеля в USD
            max_portfolio_risk: Максимальний ризик портфеля (%)
        """
        self.portfolio_size = portfolio_size
        self.max_portfolio_risk = max_portfolio_risk
        self.positions = {}
        self.trade_history = []
        self.equity_curve = []
        
        logger.info(f"💼 Ризик-менеджер ініціалізовано: ${portfolio_size}, макс. ризик {max_portfolio_risk}%")
    
    async def validate_new_position(self, symbol: str, size: float, leverage: float, 
                                  stop_loss_percent: float) -> tuple[bool, str]:
        """
        Валідація нової позиції перед відкриттям
        
        Returns:
            (можна_відкривати, причина_якщо_ні)
        """
        # Розрахунок ризику позиції
        position_risk = PositionRisk(
            symbol=symbol,
            size=size,
            risk_percent=(size / self.portfolio_size) * 100,
            leverage=leverage,
            stop_loss_distance=abs(stop_loss_percent),
            max_loss_usd=size * abs(stop_loss_percent) / 100 * leverage
        )
        
        # Перевірка 1: Розмір позиції
        if position_risk.risk_percent > 25.0:  # Максимум 25% портфеля в одній позиції
            return False, f"Позиція занадто велика: {position_risk.risk_percent:.1f}% > 25%"
        
        # Перевірка 2: Максимальний збиток
        if position_risk.max_loss_usd > (self.portfolio_size * 0.05):  # Максимум 5% на позицію
            return False, f"Потенційний збиток занадто великий: ${position_risk.max_loss_usd:.2f}"
        
        # Перевірка 3: Загальний ризик портфеля
        current_var = await self.calculate_portfolio_var()
        projected_var = current_var + (position_risk.max_loss_usd / self.portfolio_size * 100)
        
        if projected_var > self.max_portfolio_risk:
            return False, f"Перевищення лімітів VaR: {projected_var:.2f}% > {self.max_portfolio_risk}%"
        
        # Перевірка 4: Кореляційний ризик
        correlation_risk = await self.calculate_correlation_risk(symbol)
        if correlation_risk > 0.8:  # Висока кореляція з існуючими позиціями
            return False, f"Висока кореляція з портфелем: {correlation_risk:.2f}"
        
        # Перевірка 5: Кредитне плече
        if leverage > 5.0:  # Максимальне плече 5x
            return False, f"Занадто високе плече: {leverage}x > 5x"
        
        logger.info(f"✅ Позиція {symbol} пройшла валідацію: ризик {position_risk.risk_percent:.1f}%")
        return True, "OK"
    
    async def calculate_portfolio_var(self, confidence_level: float = 0.95) -> float:
        """
        Розрахунок Value at Risk портфеля
        
        Args:
            confidence_level: Рівень довіри (0.95 = 95%)
        
        Returns:
            VaR у відсотках від портфеля
        """
        if not self.positions:
            return 0.0
        
        total_risk = 0.0
        for position in self.positions.values():
            position_var = position['size'] * position['leverage'] * position['volatility']
            total_risk += position_var ** 2
        
        portfolio_var = np.sqrt(total_risk) / self.portfolio_size * 100
        return portfolio_var
    
    async def calculate_correlation_risk(self, new_symbol: str) -> float:
        """
        Розрахунок ризику кореляції з існуючими позиціями
        
        Returns:
            Максимальна кореляція з існуючими активами (0-1)
        """
        if not self.positions:
            return 0.0
        
        # Спрощений розрахунок на базі секторів
        sector_correlations = {
            'DEFI': ['UMA', 'API3', 'PENDLE', 'LDO'],
            'SOLANA': ['FIDA', 'RAY', 'SRM'],
            'AI_GAMING': ['RNDR', 'FET', 'OCEAN'],
            'INFRASTRUCTURE': ['DIA', 'GRT', 'LINK']
        }
        
        new_sector = None
        for sector, tokens in sector_correlations.items():
            if any(token in new_symbol for token in tokens):
                new_sector = sector
                break
        
        if not new_sector:
            return 0.0  # Невідомий сектор = низька кореляція
        
        # Перевіряємо чи є вже позиції з того ж сектора
        same_sector_exposure = 0.0
        for symbol, position in self.positions.items():
            for sector, tokens in sector_correlations.items():
                if sector == new_sector and any(token in symbol for token in tokens):
                    same_sector_exposure += position['size']
        
        # Нормалізуємо до 0-1
        correlation = min(same_sector_exposure / self.portfolio_size, 1.0)
        return correlation
    
    async def calculate_position_size(self, symbol: str, risk_percent: float, 
                                    stop_loss_percent: float, leverage: float = 1.0) -> float:
        """
        Розрахунок оптимального розміру позиції на базі ризику
        
        Args:
            symbol: Торгова пара
            risk_percent: Бажаний ризик (% від портфеля)
            stop_loss_percent: Відстань до стоп-лосса (%)
            leverage: Кредитне плече
        
        Returns:
            Розмір позиції в USD
        """
        # Формула: Position Size = (Portfolio * Risk%) / (Stop Loss% * Leverage)
        max_risk_usd = self.portfolio_size * (risk_percent / 100)
        position_size = max_risk_usd / (abs(stop_loss_percent) / 100)
        
        # Коригуємо на кредитне плече
        position_size = position_size / leverage
        
        # Не більше 25% портфеля
        max_position = self.portfolio_size * 0.25
        position_size = min(position_size, max_position)
        
        logger.debug(f"📊 Розмір позиції {symbol}: ${position_size:.2f} (ризик {risk_percent}%)")
        return position_size
    
    async def emergency_risk_check(self) -> tuple[bool, List[str]]:
        """
        Екстрена перевірка ризиків
        
        Returns:
            (потрібна_екстрена_дія, список_причин)
        """
        emergency_actions = []
        
        # Перевірка 1: Загальний VaR
        current_var = await self.calculate_portfolio_var()
        if current_var > self.max_portfolio_risk * 1.5:  # 150% від ліміту
            emergency_actions.append(f"Критичний VaR: {current_var:.2f}%")
        
        # Перевірка 2: Просадка портфеля
        current_drawdown = await self.calculate_current_drawdown()
        if current_drawdown > 15.0:  # Просадка більше 15%
            emergency_actions.append(f"Критична просадка: {current_drawdown:.2f}%")
        
        # Перевірка 3: Концентрація ризику
        max_position_risk = max([pos['size'] / self.portfolio_size * 100 
                               for pos in self.positions.values()], default=0)
        if max_position_risk > 35.0:  # Одна позиція більше 35%
            emergency_actions.append(f"Концентрація ризику: {max_position_risk:.1f}%")
        
        # Перевірка 4: Кількість збиткових позицій
        losing_positions = len([pos for pos in self.positions.values() 
                              if pos.get('unrealized_pnl', 0) < -5.0])
        if losing_positions >= 3:  # 3+ позиції в мінусі більше 5%
            emergency_actions.append(f"Множинні збитки: {losing_positions} позицій")
        
        return len(emergency_actions) > 0, emergency_actions
    
    async def calculate_current_drawdown(self) -> float:
        """Розрахунок поточної просадки"""
        if len(self.equity_curve) < 2:
            return 0.0
        
        peak = max(self.equity_curve)
        current = self.equity_curve[-1]
        drawdown = ((peak - current) / peak) * 100
        return max(drawdown, 0.0)
    
    async def update_position(self, symbol: str, current_price: float, unrealized_pnl: float):
        """Оновлення інформації про позицію"""
        if symbol in self.positions:
            self.positions[symbol].update({
                'current_price': current_price,
                'unrealized_pnl': unrealized_pnl,
                'last_update': datetime.now()
            })
    
    async def close_position(self, symbol: str, exit_price: float, realized_pnl: float):
        """Закриття позиції та оновлення статистики"""
        if symbol in self.positions:
            position = self.positions.pop(symbol)
            
            # Додаємо до історії
            trade_record = {
                'symbol': symbol,
                'entry_time': position['entry_time'],
                'exit_time': datetime.now(),
                'entry_price': position['entry_price'],
                'exit_price': exit_price,
                'size': position['size'],
                'realized_pnl': realized_pnl,
                'pnl_percent': (realized_pnl / position['size']) * 100
            }
            
            self.trade_history.append(trade_record)
            
            # Оновлюємо криву балансу
            current_equity = self.portfolio_size + sum([t['realized_pnl'] for t in self.trade_history])
            self.equity_curve.append(current_equity)
            
            logger.info(f"📈 Позицію {symbol} закрито: P&L ${realized_pnl:.2f}")
    
    async def get_risk_report(self) -> Dict:
        """Генерація звіту по ризиках"""
        metrics = await self.calculate_risk_metrics()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'portfolio_size': self.portfolio_size,
            'active_positions': len(self.positions),
            'total_exposure': sum([pos['size'] for pos in self.positions.values()]),
            'var_percent': metrics.portfolio_var,
            'max_drawdown': metrics.max_drawdown,
            'sharpe_ratio': metrics.sharpe_ratio,
            'correlation_risk': metrics.correlation_risk,
            'positions': list(self.positions.keys()),
            'emergency_status': await self.emergency_risk_check()
        }
    
    async def calculate_risk_metrics(self) -> RiskMetrics:
        """Розрахунок всіх метрик ризику"""
        portfolio_var = await self.calculate_portfolio_var()
        max_drawdown = await self.calculate_current_drawdown()
        
        # Коефіцієнт Шарпа (спрощений)
        if len(self.trade_history) > 0:
            returns = [t['pnl_percent'] for t in self.trade_history]
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe_ratio = mean_return / std_return if std_return > 0 else 0.0
        else:
            sharpe_ratio = 0.0
        
        total_exposure = sum([pos['size'] * pos.get('leverage', 1) for pos in self.positions.values()])
        
        # Середня кореляція портфеля
        correlations = []
        symbols = list(self.positions.keys())
        for symbol in symbols:
            corr = await self.calculate_correlation_risk(symbol)
            correlations.append(corr)
        
        correlation_risk = np.mean(correlations) if correlations else 0.0
        
        return RiskMetrics(
            portfolio_var=portfolio_var,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            total_exposure=total_exposure,
            correlation_risk=correlation_risk
        )
